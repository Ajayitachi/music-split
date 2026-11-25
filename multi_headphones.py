"""Multi Headphones - play your movie's sound on several headphones at once.

Works with Bluetooth headphones, wired earphones (3.5 mm jack or USB-C),
USB headsets and speakers. Each device gets its own volume and sync delay.
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk

import soundcard as sc  # import before tkinter widgets are created (sets up COM)

from audio_engine import Engine
from devices import classify, device_parents

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
AUTO_SOURCE = "Windows default output (automatic)"
MAX_DELAY_MS = 600


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"source": None, "devices": {}}


class App:
    def __init__(self, root):
        self.root = root
        self.engine = Engine()
        self.settings = load_settings()
        self.settings.setdefault("devices", {})
        self.speakers = []            # list of (id, display name)
        self.kinds = {}               # id -> "Bluetooth" / "Wired (USB)" ...
        self.rows = {}                # id -> widgets/vars
        self._detecting = False

        root.title("Multi Headphones")
        root.minsize(760, 420)
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Kind.TLabel", foreground="#2563eb")
        style.configure("Muted.TLabel", foreground="#6b7280")

        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Multi Headphones", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, style="Muted.TLabel",
                  text="Play the movie's sound on Bluetooth headphones and wired earphones together."
                  ).pack(anchor="w", pady=(0, 10))

        # --- source ---
        src = ttk.LabelFrame(main, text=" 1. Movie sound comes from ", padding=10)
        src.pack(fill="x")
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(src, textvariable=self.source_var, state="readonly", width=55)
        self.source_box.grid(row=0, column=0, sticky="w")
        self.source_box.bind("<<ComboboxSelected>>", lambda e: self.on_source_changed())
        ttk.Button(src, text="Windows sound settings",
                   command=lambda: os.startfile("ms-settings:sound")).grid(row=0, column=1, padx=8)
        self.level = ttk.Progressbar(src, length=160, maximum=1.0)
        self.level.grid(row=0, column=2, padx=(8, 0))
        ttk.Label(src, style="Muted.TLabel", wraplength=700, justify="left",
                  text="Leave this on 'Windows default output' unless you know you need something else. "
                       "That device keeps the original sound; everything you tick below gets a copy."
                  ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.warn_var = tk.StringVar()
        ttk.Label(src, textvariable=self.warn_var, foreground="#dc2626", wraplength=700,
                  justify="left").grid(row=2, column=0, columnspan=3, sticky="w")

        # --- outputs ---
        outs = ttk.LabelFrame(main, text=" 2. Tick the headphones / earphones that should play ", padding=10)
        outs.pack(fill="both", expand=True, pady=10)
        self.rows_frame = ttk.Frame(outs)
        self.rows_frame.pack(fill="both", expand=True)
        self.empty_label = ttk.Label(outs, style="Muted.TLabel",
                                     text="No output devices found. Connect headphones or plug in earphones.")

        # --- controls ---
        bar = ttk.Frame(main)
        bar.pack(fill="x")
        self.start_btn = ttk.Button(bar, text="▶  Start", command=self.toggle)
        self.start_btn.pack(side="left")
        self.clicks_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Sync test (beep every second)", variable=self.clicks_var,
                        command=self.on_clicks).pack(side="left", padx=14)
        ttk.Button(bar, text="Refresh devices", command=self.refresh_devices).pack(side="left")
        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        ttk.Label(main, style="Muted.TLabel", wraplength=730, justify="left",
                  text="Sync tip: turn on Sync test, wear one earbud from two devices, and raise the Delay "
                       "of the device that beeps first until both beep together. If the sound is behind the "
                       "picture, use your player's audio-delay setting (VLC: J / K keys)."
                  ).pack(anchor="w", pady=(8, 0))

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_devices()
        self.tick()
        self.root.after(3000, self.watch_devices)

    # ---------------- devices ----------------
    def scan(self):
        speakers = sc.all_speakers()
        seen, result = {}, []
        for s in speakers:
            name = s.name
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = f"{name} #{seen[name]}"
            result.append((s.id, name))
        return result

    def refresh_devices(self):
        try:
            self.speakers = self.scan()
        except Exception:
            self.speakers = []
        ids = [i for i, _ in self.speakers]
        names = [n for _, n in self.speakers]
        self.source_box["values"] = [AUTO_SOURCE] + names

        chosen = self.source_var.get() or self.settings.get("source_name") or AUTO_SOURCE
        if chosen != AUTO_SOURCE and chosen not in names:
            chosen = AUTO_SOURCE
        self.source_var.set(chosen)
        wanted = self.current_source_id()
        self.build_rows()
        if any(i not in self.kinds for i in ids):
            self.detect_kinds()
        if self.engine.running and wanted != self.engine.source_id and wanted:
            self.engine.start(wanted)
        self.apply_outputs()

    def watch_devices(self):
        try:
            ids = [i for i, _ in self.scan()]
            if ids != [i for i, _ in self.speakers]:
                self.refresh_devices()
            else:
                # follow Windows when its default output changes
                src = self.current_source_id()
                if self.engine.running and src and src != self.engine.source_id:
                    self.engine.start(src)
                    self.apply_outputs()
        except Exception:
            pass
        self.root.after(3000, self.watch_devices)

    def detect_kinds(self):
        if self._detecting:
            return
        self._detecting = True

        def work():
            parents = device_parents()
            names = dict(self.speakers)
            kinds = {i: classify(names.get(i, ""), parents.get(i.lower(), "")) for i in names}
            self.root.after(0, lambda: self._kinds_ready(kinds))

        threading.Thread(target=work, daemon=True).start()

    def _kinds_ready(self, kinds):
        self._detecting = False
        self.kinds.update(kinds)
        for dev_id, row in self.rows.items():
            row["kind"].set(self.kinds.get(dev_id, ""))

    @staticmethod
    def windows_default_id():
        try:
            return sc.default_speaker().id
        except Exception:
            return None

    def current_source_id(self):
        name = self.source_var.get()
        if name == AUTO_SOURCE:
            return self.windows_default_id()
        for i, n in self.speakers:
            if n == name:
                return i
        return None

    # ---------------- rows ----------------
    def build_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.rows = {}
        if not self.speakers:
            self.empty_label.pack(anchor="w")
            return
        self.empty_label.pack_forget()

        hdr = ("Device", "Type", "Volume", "Delay (sync)", "", "Status")
        for c, text in enumerate(hdr):
            ttk.Label(self.rows_frame, text=text, style="Muted.TLabel").grid(row=0, column=c, sticky="w", padx=4)

        for r, (dev_id, name) in enumerate(self.speakers, start=1):
            saved = self.settings["devices"].get(dev_id, {})
            row = {
                "enabled": tk.BooleanVar(value=saved.get("enabled", False)),
                "volume": tk.IntVar(value=saved.get("volume", 100)),
                "delay": tk.IntVar(value=saved.get("delay", 0)),
                "kind": tk.StringVar(value=self.kinds.get(dev_id, "…")),
                "status": tk.StringVar(value=""),
                "delay_text": tk.StringVar(),
            }
            out = self.engine.output(dev_id, name)
            row["check"] = ttk.Checkbutton(self.rows_frame, text=name, variable=row["enabled"],
                                           command=self.on_row_changed)
            row["check"].grid(row=r, column=0, sticky="w", padx=4, pady=3)
            ttk.Label(self.rows_frame, textvariable=row["kind"], style="Kind.TLabel").grid(
                row=r, column=1, sticky="w", padx=4)
            ttk.Scale(self.rows_frame, from_=0, to=150, length=110, variable=row["volume"],
                      command=lambda v, d=dev_id: self.on_slider(d)).grid(row=r, column=2, padx=4)
            ttk.Scale(self.rows_frame, from_=0, to=MAX_DELAY_MS, length=160, variable=row["delay"],
                      command=lambda v, d=dev_id: self.on_slider(d)).grid(row=r, column=3, padx=4)
            ttk.Label(self.rows_frame, textvariable=row["delay_text"], width=7).grid(row=r, column=4, sticky="w")
            ttk.Label(self.rows_frame, textvariable=row["status"], style="Muted.TLabel", width=26).grid(
                row=r, column=5, sticky="w", padx=4)
            self.rows[dev_id] = row
            self.sync_output(dev_id, out)

    def sync_output(self, dev_id, out=None):
        row = self.rows[dev_id]
        out = out or self.engine.outputs[dev_id]
        out.delay_ms = int(float(row["delay"].get()))
        out.volume = int(float(row["volume"].get())) / 100.0
        row["delay_text"].set(f"{out.delay_ms} ms")

    def on_slider(self, dev_id):
        self.sync_output(dev_id)
        self.save_settings()

    def on_row_changed(self):
        self.apply_outputs()
        self.save_settings()

    def on_source_changed(self):
        src = self.current_source_id()
        if self.engine.running and src:
            self.engine.start(src)
        self.apply_outputs()
        self.save_settings()

    def on_clicks(self):
        self.engine.sync_clicks = self.clicks_var.get()

    def apply_outputs(self):
        src = self.current_source_id()
        for dev_id, row in self.rows.items():
            out = self.engine.outputs[dev_id]
            is_source = dev_id == src
            row["check"].state(["disabled"] if is_source else ["!disabled"])
            want = self.engine.running and row["enabled"].get() and not is_source
            if want and not out.running:
                out.start()
            elif not want and out.running:
                out.stop()

    # ---------------- start / stop ----------------
    def toggle(self):
        if self.engine.running:
            self.engine.stop()
            self.start_btn.config(text="▶  Start")
        else:
            src = self.current_source_id()
            if not src:
                self.status_var.set("Pick where the movie sound comes from first")
                return
            self.engine.start(src)
            self.start_btn.config(text="■  Stop")
        self.apply_outputs()

    def tick(self):
        self.level["value"] = min(self.engine.level, 1.0)
        src = self.current_source_id()
        default = self.windows_default_id()
        if self.source_var.get() != AUTO_SOURCE and src and default and src != default:
            self.warn_var.set("⚠ Windows is playing sound on a different device, so this source is "
                              "probably silent. Pick 'Windows default output', or switch Windows' output "
                              "to this device in Windows sound settings.")
        else:
            self.warn_var.set("")
        for dev_id, row in self.rows.items():
            out = self.engine.outputs.get(dev_id)
            if dev_id == src:
                row["status"].set("original sound (source)")
            elif out and out.running:
                row["status"].set(out.status)
            else:
                row["status"].set("")
        if self.engine.running:
            n = sum(1 for o in self.engine.outputs.values() if o.running)
            self.status_var.set(f"{self.engine.status.capitalize()} · sending to {n} device(s)")
        else:
            self.status_var.set("Stopped")
        self.root.after(200, self.tick)

    # ---------------- settings ----------------
    def save_settings(self):
        self.settings["source_name"] = self.source_var.get()
        for dev_id, row in self.rows.items():
            self.settings["devices"][dev_id] = {
                "enabled": bool(row["enabled"].get()),
                "volume": int(float(row["volume"].get())),
                "delay": int(float(row["delay"].get())),
            }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError:
            pass

    def on_close(self):
        self.save_settings()
        self.engine.stop()
        self.root.destroy()


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)   # sharp text on high-DPI screens
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
