"""End-to-end self test for Multi Headphones.

Opens the real app (with a throw-away settings file), ticks every device, presses Start,
plays a 3-second tone on the Windows default output (the "movie"), and checks via loopback
that every other output received it. You will hear the tone on your devices.

Run:  .venv\\Scripts\\python.exe tests\\self_test.py
"""
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import soundcard as sc

import multi_headphones as m
from audio_engine import find_loopback

m.SETTINGS_FILE = os.path.join(tempfile.gettempdir(), "mh_self_test_settings.json")
if os.path.exists(m.SETTINGS_FILE):
    os.remove(m.SETTINGS_FILE)

import tkinter as tk

root = tk.Tk()
app = m.App(root)
results = {}


def movie_and_measure():
    default = sc.default_speaker()
    targets = [(i, n) for i, n in app.speakers if i != default.id]
    sr = 48000
    t = np.arange(int(sr * 3)) / sr
    tone = (0.15 * np.sin(2 * np.pi * 440 * t) * (np.sin(2 * np.pi * 2 * t) > 0)).astype(np.float32)
    peaks = {}

    def measure(dev_id):
        try:
            with find_loopback(dev_id).recorder(samplerate=sr, channels=2) as rec:
                time.sleep(0.2)
                peaks[dev_id] = float(np.abs(rec.record(numframes=int(sr * 2.4))).max())
        except Exception as exc:
            peaks[dev_id] = repr(exc)

    threads = [threading.Thread(target=measure, args=(i,)) for i, _ in targets]
    for th in threads:
        th.start()
    default.play(tone, samplerate=sr)
    for th in threads:
        th.join()
    results["default"] = default.name
    results["rows"] = [(n, app.kinds.get(i, "?"), app.engine.outputs[i].status, peaks[i]) for i, n in targets]
    root.after(0, finish)


def finish():
    print("Source (Windows default):", results["default"])
    failed = 0
    for name, kind, status, peak in results["rows"]:
        ok = isinstance(peak, float) and peak > 0.02
        failed += not ok
        shown = round(peak, 3) if isinstance(peak, float) else peak
        print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} {kind:18s} status={status:10s} peak={shown}")
    print("RESULT:", "all outputs received the sound" if not failed else f"{failed} output(s) got no sound")
    app.on_close()


def go():
    for row in app.rows.values():
        row["enabled"].set(True)
    app.on_row_changed()
    app.toggle()
    root.after(2000, lambda: threading.Thread(target=movie_and_measure, daemon=True).start())


root.after(4000, go)
root.mainloop()
