"""Audio engine: copies the sound of one Windows output device to many others.

The "source" is the device Windows plays the movie on. Its sound is captured
with WASAPI loopback and sent to every enabled output (Bluetooth headphones,
wired earphones, USB headsets, speakers ...). Each output has its own queue,
delay and volume, and a small drift controller keeps every device at exactly
its chosen delay for the whole movie.
"""

import collections
import sys
import threading
import time
import warnings

import numpy as np
import soundcard as sc

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)
# Let audio threads take turns more often (default 5 ms is long when 5 threads share one 10 ms block).
sys.setswitchinterval(0.002)

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK = 480                       # 10 ms per block
# Buffer sizes. Small buffers = low delay but crackle when the PC is busy (several devices at once).
# So every output starts small and grows its own buffers by itself whenever it runs dry, until the
# crackle stops. Measured with OnePlus Nord Buds 3 Pro: 20/20 ms adds ~120-150 ms over the source,
# 40/40 ms ~200 ms; with 4 devices the 20 ms queue ran dry a few times (heard as crackle).
JITTER_MS = 20                    # starting safety buffer on top of the user's delay
MAX_EXTRA_MS = 100                # how far the safety buffer may grow on its own
PLAYER_MS = 30                    # starting device buffer
MAX_PLAYER_MS = 80
GROW_MS = 10
PLAYER_BUFFER = int(SAMPLE_RATE * PLAYER_MS / 1000)
CAPTURE_BUFFER = SAMPLE_RATE // 100
MAX_QUEUE_SECONDS = 3.0


def find_speaker(device_id):
    """Exact id lookup (soundcard's own lookup falls back to fuzzy name matching,
    which could pick the wrong device when ours is unplugged)."""
    for spk in sc.all_speakers():
        if spk.id == device_id:
            return spk
    raise LookupError("device not connected")


def find_loopback(device_id):
    for mic in sc.all_microphones(include_loopback=True):
        if mic.isloopback and mic.id == device_id:
            return mic
    raise LookupError("device not connected")


def _stretch(chunk, new_len):
    """Resample a block to new_len frames (tiny speed change, inaudible)."""
    old = np.arange(chunk.shape[0])
    new = np.linspace(0, chunk.shape[0] - 1, new_len)
    return np.stack([np.interp(new, old, chunk[:, c]) for c in range(chunk.shape[1])],
                    axis=1).astype(np.float32)


class Output:
    """One listening device (headphone, earphone, speaker)."""

    def __init__(self, device_id, name):
        self.device_id = device_id
        self.name = name
        self.delay_ms = 0
        self.volume = 1.0
        self.status = "off"
        self.level = 0.0             # 0..1 loudness of what this device is playing, for the meter
        self.starved = 0             # times our queue ran empty while the movie was playing (crackle)
        self.device_empty = 0        # times the device buffer ran empty (we wrote too late: crackle)
        self.extra_ms = 0            # safety buffer added automatically after crackles
        self.player_ms = PLAYER_MS   # device buffer, grows automatically after crackles
        self._dry_since = None
        self._queue = collections.deque()
        self._frames = 0
        self._lock = threading.Lock()
        self._priming = True
        self._correcting = 0
        self._running = False
        self._thread = None

    # ---- called by the capture thread ----
    def push(self, block):
        if not self._running:
            return
        now = time.monotonic()
        dry = self._dry_since
        if dry is not None:
            self._dry_since = None
            if now - dry < 0.15:
                # we ran dry but sound was back within 150 ms: a real hiccup (heard as a click),
                # so keep a bigger safety buffer from now on
                self.starved += 1
                self.extra_ms = min(self.extra_ms + GROW_MS, MAX_EXTRA_MS)
        with self._lock:
            self._queue.append(block)
            self._frames += block.shape[0]
            limit = int(MAX_QUEUE_SECONDS * SAMPLE_RATE) + self._target()
            while self._frames > limit and self._queue:
                self._frames -= self._queue.popleft().shape[0]

    # ---- lifecycle ----
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name=f"out-{self.name}", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        with self._lock:
            self._queue.clear()
            self._frames = 0
        self.status = "off"
        self.level = 0.0

    @property
    def running(self):
        return self._running

    # ---- internals ----
    def _target(self):
        return int((self.delay_ms + JITTER_MS + self.extra_ms) * SAMPLE_RATE / 1000)

    @property
    def safety_ms(self):
        """How much buffering was added automatically to stop crackling."""
        return self.extra_ms + self.player_ms - PLAYER_MS

    def _pop(self, n):
        out = np.zeros((n, CHANNELS), dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < n and self._queue:
                head = self._queue[0]
                take = min(n - filled, head.shape[0])
                out[filled:filled + take] = head[:take]
                filled += take
                if take == head.shape[0]:
                    self._queue.popleft()
                else:
                    self._queue[0] = head[take:]
            self._frames -= filled
        return out

    def _drop(self, n):
        with self._lock:
            while n > 0 and self._queue:
                head = self._queue[0]
                if head.shape[0] <= n:
                    n -= head.shape[0]
                    self._frames -= head.shape[0]
                    self._queue.popleft()
                else:
                    self._queue[0] = head[n:]
                    self._frames -= n
                    n = 0

    def _next_chunk(self):
        silence = np.zeros((BLOCK, CHANNELS), dtype=np.float32)
        target = self._target()
        depth = self._frames
        big = SAMPLE_RATE // 10            # 100 ms: jump instead of slow correction

        if self._priming:
            if depth < target:
                return silence              # build up the requested delay
            self._priming = False
        if depth == 0:
            # Ran dry. push() decides if it was a glitch (sound comes back right away) or just the
            # movie stopping/pausing (sound stays away).
            if self._dry_since is None:
                self._dry_since = time.monotonic()
            self._priming = True            # rebuild delay
            return silence

        err = depth - target
        if err > big:
            self._drop(err)                 # delay was lowered: skip ahead
            err = 0
        elif err < -big:
            self._priming = True            # delay was raised: insert silence
            return silence

        chunk = self._pop(BLOCK)
        # Slow drift correction (device clocks are never exactly equal):
        # play 1 frame fewer/more per 10 ms block until we are back on target.
        tol_on, tol_off = SAMPLE_RATE * 15 // 1000, SAMPLE_RATE * 5 // 1000
        if self._correcting == 0 and abs(err) > tol_on:
            self._correcting = 1 if err > 0 else -1
        elif self._correcting and abs(err) < tol_off:
            self._correcting = 0
        if self._correcting:
            chunk = _stretch(chunk, BLOCK - self._correcting)

        if self.volume != 1.0:
            chunk = np.clip(chunk * self.volume, -1.0, 1.0)
        return chunk

    def _run(self):
        while self._running:
            try:
                speaker = find_speaker(self.device_id)
                size = self.player_ms
                with speaker.player(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                    blocksize=int(SAMPLE_RATE * size / 1000)) as player:
                    self._priming = True
                    self.status = "playing"
                    while self._running:
                        if not self._priming and player.currentpadding == 0:
                            # device played everything we gave it: we were late (click).
                            # Use a bigger device buffer (re-open the device to apply it).
                            self.device_empty += 1
                            if self.player_ms < MAX_PLAYER_MS:
                                self.player_ms = min(self.player_ms + GROW_MS, MAX_PLAYER_MS)
                                break
                        chunk = self._next_chunk()
                        self.level = max(float(np.abs(chunk).max()), self.level * 0.85)
                        player.play(chunk)
            except Exception as exc:   # device unplugged / turned off
                self.status = f"waiting for device ({exc.__class__.__name__})"
                for _ in range(20):
                    if not self._running:
                        break
                    time.sleep(0.1)
        self.status = "off"


class Engine:
    """Captures the source device and fans its sound out to the outputs."""

    def __init__(self):
        self.outputs = {}            # device_id -> Output
        self.source_id = None
        self.level = 0.0             # 0..1 loudness of the source, for the meter
        self.status = "stopped"
        self.sync_clicks = False
        self._running = False
        self._thread = None
        self._beeper = None
        self._click_pos = 0

    def output(self, device_id, name):
        if device_id not in self.outputs:
            self.outputs[device_id] = Output(device_id, name)
        out = self.outputs[device_id]
        out.name = name
        return out

    @property
    def running(self):
        return self._running

    def start(self, source_id):
        self.stop()
        self.source_id = source_id
        self._running = True
        self._thread = threading.Thread(target=self._capture, name="capture", daemon=True)
        self._thread.start()
        self._beeper = threading.Thread(target=self._beep_loop, name="beeper", daemon=True)
        self._beeper.start()

    def stop(self):
        self._running = False
        for th in (self._thread, getattr(self, "_beeper", None)):
            if th:
                th.join(timeout=2)
        self._thread = self._beeper = None
        for out in self.outputs.values():
            out.stop()
        self.level = 0.0
        self.status = "stopped"

    def _click_block(self):
        """10 ms of the sync signal: a short 1 kHz beep once a second, silence otherwise."""
        period = SAMPLE_RATE
        length = SAMPLE_RATE // 100
        pos = (self._click_pos + np.arange(BLOCK)) % period
        beep = np.where(pos < length, 0.4 * np.sin(2 * np.pi * 1000 * pos / SAMPLE_RATE), 0.0)
        self._click_pos = (self._click_pos + BLOCK) % period
        return np.repeat(beep[:, None], CHANNELS, axis=1).astype(np.float32)

    def _beep_loop(self):
        """Sync test: play the beep ON the source device, like a movie would. The source plays it
        directly and the capture copies it to every output, so all devices get the same beep through
        the same path as the movie sound."""
        while self._running:
            if not self.sync_clicks:
                time.sleep(0.1)
                continue
            src = self.source_id
            try:
                with find_speaker(src).player(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                              blocksize=PLAYER_BUFFER) as player:
                    self._click_pos = 0
                    while self._running and self.sync_clicks and self.source_id == src:
                        player.play(self._click_block())
            except Exception:
                time.sleep(1)

    def _capture(self):
        while self._running:
            try:
                mic = find_loopback(self.source_id)
                with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                  blocksize=CAPTURE_BUFFER) as rec:
                    self.status = "running"
                    while self._running:
                        block = rec.record(numframes=BLOCK).astype(np.float32)
                        peak = float(np.abs(block).max()) if block.size else 0.0
                        self.level = max(peak, self.level * 0.9)
                        for out in list(self.outputs.values()):
                            out.push(block)
            except Exception as exc:
                self.status = f"source not available ({exc.__class__.__name__})"
                time.sleep(1)
        self.status = "stopped"
