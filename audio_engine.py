"""Audio engine: copies the sound of one Windows output device to many others.

The "source" is the device Windows plays the movie on. Its sound is captured
with WASAPI loopback and sent to every enabled output (Bluetooth headphones,
wired earphones, USB headsets, speakers ...). Each output has its own queue,
delay and volume, and a small drift controller keeps every device at exactly
its chosen delay for the whole movie.
"""

import collections
import threading
import time
import warnings

import numpy as np
import soundcard as sc

warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK = 480                       # 10 ms per block
JITTER_MS = 40                    # safety buffer on top of the user's delay
PLAYER_BUFFER = int(SAMPLE_RATE * 0.04)
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

    @property
    def running(self):
        return self._running

    # ---- internals ----
    def _target(self):
        return int((self.delay_ms + JITTER_MS) * SAMPLE_RATE / 1000)

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
            self._priming = True            # source stalled: rebuild delay
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
                with speaker.player(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                    blocksize=PLAYER_BUFFER) as player:
                    self._priming = True
                    self.status = "playing"
                    while self._running:
                        player.play(self._next_chunk())
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

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        for out in self.outputs.values():
            out.stop()
        self.level = 0.0
        self.status = "stopped"

    def _add_clicks(self, block):
        """Short beep once a second, to line up the delays by ear."""
        period = SAMPLE_RATE
        length = SAMPLE_RATE // 100
        pos = (self._click_pos + np.arange(block.shape[0])) % period
        beep = np.where(pos < length, 0.5 * np.sin(2 * np.pi * 1000 * pos / SAMPLE_RATE), 0.0)
        block = block + beep[:, None].astype(np.float32)
        self._click_pos = (self._click_pos + block.shape[0]) % period
        return block

    def _capture(self):
        while self._running:
            try:
                mic = find_loopback(self.source_id)
                with mic.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                  blocksize=SAMPLE_RATE // 50) as rec:
                    self.status = "running"
                    while self._running:
                        block = rec.record(numframes=BLOCK).astype(np.float32)
                        if self.sync_clicks:
                            block = self._add_clicks(block)
                        peak = float(np.abs(block).max()) if block.size else 0.0
                        self.level = max(peak, self.level * 0.9)
                        for out in list(self.outputs.values()):
                            out.push(block)
            except Exception as exc:
                self.status = f"source not available ({exc.__class__.__name__})"
                time.sleep(1)
        self.status = "stopped"
