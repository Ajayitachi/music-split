"""Multi Headphones - play your movie's sound on several headphones at once.

Works with Bluetooth headphones, wired earphones (3.5 mm jack or USB-C),
USB headsets and speakers. Each device gets its own volume and sync delay.
The window looks like a small audio mixer: one channel strip per device.
"""

import json
import math
import os
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

import soundcard as sc  # import before tkinter widgets are created (sets up COM)
import sv_ttk

from audio_engine import Engine
from devices import classify, device_parents, is_virtual

APP_NAME = "Multi Headphones"
APP_VERSION = "1.0"
FROZEN = getattr(sys, "frozen", False)
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
if FROZEN:   # installed .exe: keep settings in %APPDATA%, the program folder may be read-only
    DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
ICON_FILE = os.path.join(RES_DIR, "assets", "icon.ico")
AUTO_SOURCE = "Windows default output (automatic)"
MAX_DELAY_MS = 600
DELAY_STEP_MS = 10
MAX_VOLUME = 150
FADER_LEN = 150

# colours: dark mixer console
BG = "#111318"
PANEL = "#181b22"
STRIP = "#1e222b"
STRIP_ON = "#1f2a38"
STRIP_SRC = "#261f38"
BORDER = "#2b303b"
BORDER_ON = "#3b82c4"
BORDER_SRC = "#8b5cf6"
TEXT = "#f2f4f8"
MUTED = "#8b93a3"
ACCENT = "#4cc2ff"
PURPLE = "#a78bfa"
GREEN = "#4ade80"
YELLOW = "#facc15"
RED = "#f87171"
LED_OFF = "#262b35"
CHIP = "#2a3040"

# Segoe Fluent Icons / MDL2 glyphs
G_HEADPHONE, G_SPEAKER, G_MONITOR, G_SETTINGS, G_REFRESH, G_PLAY, G_STOP = (
    "", "", "", "", "", "", "")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"source": None, "devices": {}}


def pick_font(*names):
    have = set(tkfont.families())
    for n in names:
        if n in have:
            return n
    return "TkDefaultFont"


def glyph_for(kind, name):
    n = name.lower()
    if kind == "HDMI / monitor":
        return G_MONITOR
    if kind == "Bluetooth" or any(w in n for w in ("headphone", "headset", "earphone", "buds", "airpods")):
        return G_HEADPHONE
    return G_SPEAKER


def split_name(name):
    """'Headphones (OnePlus Nord Buds 3 Pro)' -> ('OnePlus Nord Buds 3 Pro', 'Headphones')."""
    if name.endswith(")") and " (" in name:
        head, _, rest = name.partition(" (")
        return rest[:-1], head
    return name, ""


def to_meter(level):
    """Peak 0..1 -> 0..1 on a -48..0 dB scale (how mixers show loudness)."""
    if level <= 1e-4:
        return 0.0
    return max(0.0, min(1.0, (20 * math.log10(level) + 48) / 48))


class LedMeter(tk.Canvas):
    """Vertical LED-style level meter: green, then yellow, then red at the top."""

    def __init__(self, parent, bg, height=190, width=12, segments=22):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        self.n = segments
        gap = 2
        seg_h = (height - gap * (segments - 1)) / segments
        self.colors, self.items = [], []
        for i in range(segments):          # i = 0 is the bottom LED
            y1 = height - i * (seg_h + gap)
            frac = i / (segments - 1)
            self.colors.append(RED if frac > 0.86 else YELLOW if frac > 0.68 else GREEN)
            self.items.append(self.create_rectangle(0, y1 - seg_h, width, y1, fill=LED_OFF, width=0))
        self.lit = 0

    def set(self, value):
        lit = round(max(0.0, min(1.0, value)) * self.n)
        if lit == self.lit:
            return
        for i in range(min(lit, self.lit), max(lit, self.lit)):
            self.itemconfigure(self.items[i], fill=self.colors[i] if i < lit else LED_OFF)
        self.lit = lit


class IconBadge(tk.Canvas):
    """Round device icon that lights up when the channel is on."""

    def __init__(self, parent, bg, glyph, font, size=58):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.ring = self.create_oval(2, 2, size - 2, size - 2, outline=BORDER, width=2, fill=CHIP)
        self.text = self.create_text(size / 2, size / 2 + 1, text=glyph, font=font, fill=MUTED)

    def light(self, color):
        if color:
            self.itemconfigure(self.ring, outline=color, fill="#16202c")
            self.itemconfigure(self.text, fill=color)
        else:
            self.itemconfigure(self.ring, outline=BORDER, fill=CHIP)
            self.itemconfigure(self.text, fill=MUTED)

    def set_glyph(self, glyph):
        self.itemconfigure(self.text, text=glyph)


class PillButton(tk.Canvas):
    """Big rounded Start / Stop button."""

    def __init__(self, parent, command, font, icon_font, width=176, height=50):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0,
                         bd=0, cursor="hand2")
        self.w, self.h, self.command = width, height, command
        r = height / 2
        self.shape = self.create_polygon(self._pill(r), smooth=True, fill=ACCENT, outline="")
        self.icon = self.create_text(width / 2 - 30, height / 2 + 1, font=icon_font, fill="#06121c")
        self.label = self.create_text(width / 2 - 14, height / 2, font=font, fill="#06121c", anchor="w")
        self.color = ACCENT
        self.hover = False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.set(False)

    def _pill(self, r):
        w, h = self.w, self.h
        return [r, 0, w - r, 0, w, 0, w, h / 2, w, h, w - r, h, r, h, 0, h, 0, h / 2, 0, 0, r, 0]

    def _hover(self, on):
        self.hover = on
        self.itemconfigure(self.shape, fill=self._shade(self.color, 1.12 if on else 1.0))

    @staticmethod
    def _shade(color, k):
        c = [min(255, int(int(color[i:i + 2], 16) * k)) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(c)

    def set(self, running):
        self.color = RED if running else ACCENT
        self.itemconfigure(self.icon, text=G_STOP if running else G_PLAY)
        self.itemconfigure(self.label, text="STOP" if running else "START")
        self._hover(self.hover)


class App:
    def __init__(self, root):
        self.root = root
        self.engine = Engine()
        self.settings = load_settings()
        self.settings.setdefault("devices", {})
        self.speakers = []            # list of (id, display name)
        self.kinds = {}               # id -> "Bluetooth" / "Wired (USB)" ...
        self.rows = {}                # id -> widgets/vars of that channel strip
        self._built_source = None
        self._detecting = False

        root.title(APP_NAME)
        root.configure(bg=BG)
        root.minsize(900, 700)
        root.geometry("1120x800")
        if os.path.exists(ICON_FILE):
            try:
                root.iconbitmap(default=ICON_FILE)
            except tk.TclError:
                pass
        sv_ttk.set_theme("dark")
        self.dark_title_bar()

        ui = pick_font("Segoe UI Variable Text", "Segoe UI")
        disp = pick_font("Segoe UI Variable Display", "Segoe UI")
        icons = pick_font("Segoe Fluent Icons", "Segoe MDL2 Assets")
        self.f_icon = (icons, 20)
        self.f_icon_s = (icons, 11)
        self.f_title = (disp, 19, "bold")
        self.f_head = (disp, 12, "bold")
        self.f_name = (ui, 10, "bold")
        self.f_body = (ui, 10)
        self.f_small = (ui, 9)
        self.f_tiny = (ui, 8, "bold")
        self.f_value = (disp, 14, "bold")
        self.setup_styles()

        # --- top bar ---
        top = tk.Frame(root, bg=PANEL, padx=22, pady=14)
        top.pack(fill="x")
        logo = IconBadge(top, PANEL, G_HEADPHONE, (icons, 18), size=46)
        logo.light(ACCENT)
        logo.pack(side="left")
        titles = tk.Frame(top, bg=PANEL)
        titles.pack(side="left", padx=(12, 0))
        tk.Label(titles, text=APP_NAME, font=self.f_title, fg=TEXT, bg=PANEL).pack(anchor="w")
        tk.Label(titles, text="One movie · many headphones", font=self.f_small, fg=MUTED, bg=PANEL).pack(anchor="w")

        self.start_btn = PillButton(top, self.toggle, (disp, 12, "bold"), (icons, 13))
        self.start_btn.pack(side="right")
        stat = tk.Frame(top, bg=PANEL)
        stat.pack(side="right", padx=(0, 18))
        self.status_dot = tk.Label(stat, text="●", font=(ui, 12), fg=MUTED, bg=PANEL)
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar(value="Stopped")
        tk.Label(stat, textvariable=self.status_var, font=self.f_body, fg=TEXT, bg=PANEL).pack(side="left", padx=4)

        # --- source bar ---
        srcbar = tk.Frame(root, bg=BG, padx=22, pady=14)
        srcbar.pack(fill="x")
        tk.Label(srcbar, text="MOVIE SOUND FROM", font=self.f_tiny, fg=MUTED, bg=BG).grid(
            row=0, column=0, sticky="w")
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(srcbar, textvariable=self.source_var, state="readonly", width=46)
        self.source_box.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.source_box.bind("<<ComboboxSelected>>", lambda e: self.on_source_changed())
        ttk.Button(srcbar, text=G_SETTINGS, style="Icon.TButton", width=3,
                   command=lambda: os.startfile("ms-settings:sound")).grid(row=1, column=1, padx=(8, 0),
                                                                          pady=(4, 0))
        tk.Label(srcbar, text="Windows sound settings", font=self.f_small, fg=MUTED, bg=BG).grid(
            row=1, column=2, sticky="w", padx=(6, 0), pady=(4, 0))
        srcbar.columnconfigure(3, weight=1)
        opts = tk.Frame(srcbar, bg=BG)
        opts.grid(row=1, column=4, sticky="e", pady=(4, 0))
        self.show_virtual = tk.BooleanVar(value=self.settings.get("show_virtual", False))
        ttk.Checkbutton(opts, text="Virtual devices", style="Bg.Switch.TCheckbutton",
                        variable=self.show_virtual, command=self.on_show_virtual).pack(side="left", padx=(0, 14))
        self.clicks_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Sync beep", style="Bg.Switch.TCheckbutton",
                        variable=self.clicks_var, command=self.on_clicks).pack(side="left", padx=(0, 14))
        ttk.Button(opts, text=G_REFRESH, style="Icon.TButton", width=3,
                   command=self.refresh_devices).pack(side="left")
        self.warn_var = tk.StringVar()
        tk.Label(srcbar, textvariable=self.warn_var, font=self.f_small, fg=RED, bg=BG, justify="left",
                 wraplength=900).grid(row=2, column=0, columnspan=5, sticky="w")

        # --- mixer: channel strips side by side, scrolls sideways when there are many ---
        mixer = tk.Frame(root, bg=BG, padx=22)
        mixer.pack(fill="both", expand=True)
        self.strip_canvas = tk.Canvas(mixer, bg=BG, highlightthickness=0, bd=0)
        self.hbar = ttk.Scrollbar(mixer, orient="horizontal", command=self.strip_canvas.xview)
        self.strip_canvas.configure(xscrollcommand=self.hbar.set)
        self.hbar.pack(side="bottom", fill="x")
        self.strip_canvas.pack(fill="both", expand=True)
        self.rows_frame = tk.Frame(self.strip_canvas, bg=BG)
        self.strip_canvas.create_window(0, 0, window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", lambda e: self.strip_canvas.configure(
            scrollregion=self.strip_canvas.bbox("all")))
        self.strip_canvas.bind_all("<MouseWheel>", self.on_wheel)

        # --- footer ---
        foot = tk.Frame(root, bg=PANEL, padx=22, pady=10)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, font=self.f_small, fg=MUTED, bg=PANEL, justify="left", wraplength=980, anchor="w",
                 text="Sync: turn on Sync beep, wear one earbud from two devices, and raise the Delay of the one "
                      "that beeps first until both beep together. Bluetooth is always a little behind wired.  "
                      "Sound behind the picture? Use your player's audio delay (VLC: J / K)."
                 ).pack(side="left", fill="x", expand=True)
        tk.Label(foot, text=f"v{APP_VERSION}", font=self.f_small, fg=MUTED, bg=PANEL).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_devices()
        self.tick()
        self.tick_meters()
        self.root.after(3000, self.watch_devices)

    # ---------------- look ----------------
    def dark_title_bar(self):
        try:
            from ctypes import byref, c_int, sizeof, windll
            self.root.update_idletasks()
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            value = c_int(1)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(value), sizeof(value))  # immersive dark mode
        except Exception:
            pass

    def setup_styles(self):
        s = ttk.Style()
        s.configure("Icon.TButton", font=self.f_icon_s, padding=(6, 4))
        s.configure("Small.TButton", font=self.f_body, padding=(0, 0))
        s.configure("Bg.Switch.TCheckbutton", background=BG, font=self.f_small)
        for name, bg in (("Strip", STRIP), ("StripOn", STRIP_ON)):
            s.configure(f"{name}.Switch.TCheckbutton", background=bg)
            s.configure(f"{name}.Vertical.TScale", background=bg)
            s.configure(f"{name}.Horizontal.TScale", background=bg)

    def strip(self, bg, border):
        outer = tk.Frame(self.rows_frame, bg=border, padx=1, pady=1)
        outer.pack(side="left", fill="y", padx=(0, 12), pady=(0, 10))
        inner = tk.Frame(outer, bg=bg, padx=14, pady=14, width=206)
        inner.pack(fill="both", expand=True)
        inner.columnconfigure(0, weight=1)
        return outer, inner

    def on_wheel(self, event):
        try:
            if str(event.widget).startswith(str(self.strip_canvas)) and self.strip_canvas.xview() != (0.0, 1.0):
                self.strip_canvas.xview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass

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
                if src != self._built_source:
                    self.save_settings()
                    self.build_rows()
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
            row["kind"].set(self.kind_text(dev_id, row["name"]))
            row["icon"].set_glyph(glyph_for(self.kinds.get(dev_id, ""), row["name"]))

    def kind_text(self, dev_id, name):
        if is_virtual(name):
            return "VIRTUAL"
        return self.kinds.get(dev_id, "detecting…").upper()

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

    def visible(self, dev_id, name, src):
        return dev_id == src or self.show_virtual.get() or not is_virtual(name)

    # ---------------- channel strips ----------------
    def build_rows(self):
        for w in self.rows_frame.winfo_children():
            w.destroy()
        self.rows = {}
        src = self.current_source_id()
        self._built_source = src
        shown = [(i, n) for i, n in self.speakers if self.visible(i, n, src)]
        if not shown:
            tk.Label(self.rows_frame, bg=BG, fg=MUTED, font=self.f_body,
                     text="No headphones found. Pair Bluetooth headphones in Windows Settings "
                          "or plug in earphones, then press refresh.").pack(anchor="w", pady=20)
            return
        shown.sort(key=lambda x: x[0] != src)          # source strip first
        for dev_id, name in shown:
            self.build_strip(dev_id, name, dev_id == src)

    def strip_header(self, c, bg, dev_id, name, row):
        row["icon"] = IconBadge(c, bg, glyph_for(self.kinds.get(dev_id, ""), name), self.f_icon, size=50)
        row["icon"].grid(row=0, column=0, pady=(0, 6))
        title, sub = split_name(name)
        tk.Label(c, text=title, font=self.f_name, fg=TEXT, bg=bg, wraplength=176, justify="center",
                 height=2).grid(row=1, column=0)
        chip = tk.Frame(c, bg=bg)
        chip.grid(row=2, column=0, pady=(2, 8))
        tk.Label(chip, textvariable=row["kind"], font=self.f_tiny, fg=MUTED, bg=CHIP, padx=8, pady=2).pack(
            side="left")
        if sub:
            tk.Label(chip, text=sub.upper(), font=self.f_tiny, fg=MUTED, bg=CHIP, padx=8, pady=2).pack(
                side="left", padx=(4, 0))

    def build_strip(self, dev_id, name, is_source):
        saved = self.settings["devices"].get(dev_id, {})
        row = {
            "name": name,
            "is_source": is_source,
            "enabled": tk.BooleanVar(value=saved.get("enabled", False)),
            "volume": tk.IntVar(value=saved.get("volume", 100)),
            "delay": tk.IntVar(value=saved.get("delay", 0)),
            "kind": tk.StringVar(value=self.kind_text(dev_id, name)),
            "status": tk.StringVar(value=""),
            "delay_text": tk.StringVar(),
            "vol_text": tk.StringVar(),
        }
        out = self.engine.output(dev_id, name)

        if is_source:
            outer, c = self.strip(STRIP_SRC, BORDER_SRC)
            row["outer"], row["card"] = outer, c
            self.strip_header(c, STRIP_SRC, dev_id, name, row)
            row["icon"].light(PURPLE)
            tk.Label(c, text="SOURCE", font=self.f_tiny, fg="#1b1130", bg=PURPLE, padx=10, pady=3).grid(
                row=3, column=0, pady=(0, 10))
            row["meter"] = LedMeter(c, STRIP_SRC, height=FADER_LEN, width=16)
            row["meter"].grid(row=4, column=0)
            tk.Label(c, text="Plays the movie directly", font=self.f_name, fg=TEXT, bg=STRIP_SRC,
                     justify="center").grid(row=5, column=0, pady=(10, 0))
            tk.Label(c, text="Volume: use the Windows\nvolume for this one", font=self.f_small, fg=MUTED,
                     bg=STRIP_SRC, justify="center").grid(row=6, column=0, pady=(6, 0))
            self.rows[dev_id] = row
            self.sync_output(dev_id, out)
            return

        on = row["enabled"].get()
        bg = STRIP_ON if on else STRIP
        outer, c = self.strip(bg, BORDER_ON if on else BORDER)
        row["outer"], row["card"] = outer, c
        self.strip_header(c, bg, dev_id, name, row)
        row["icon"].light(ACCENT if on else None)
        st = "StripOn" if on else "Strip"
        row["switch"] = ttk.Checkbutton(c, text="", style=f"{st}.Switch.TCheckbutton", variable=row["enabled"],
                                        command=lambda d=dev_id: self.on_row_changed(d))
        row["switch"].grid(row=3, column=0, pady=(0, 10))

        fader = tk.Frame(c, bg=bg)
        fader.grid(row=4, column=0)
        row["meter"] = LedMeter(fader, bg, height=FADER_LEN, width=12)
        row["meter"].pack(side="left", padx=(0, 10))
        ttk.Scale(fader, from_=MAX_VOLUME, to=0, orient="vertical", length=FADER_LEN, variable=row["volume"],
                  style=f"{st}.Vertical.TScale",
                  command=lambda v, d=dev_id: self.on_slider(d)).pack(side="left")
        vol = tk.Frame(c, bg=bg)
        vol.grid(row=5, column=0, pady=(6, 0))
        tk.Label(vol, textvariable=row["vol_text"], font=self.f_value, fg=TEXT, bg=bg).pack(side="left")
        tk.Label(vol, text=" VOLUME", font=self.f_tiny, fg=MUTED, bg=bg).pack(side="left", pady=(4, 0))

        dl = tk.Frame(c, bg=bg)
        dl.grid(row=7, column=0, pady=(10, 0), sticky="ew")
        dl.columnconfigure(1, weight=1)
        ttk.Button(dl, text="−", style="Small.TButton", width=2,
                   command=lambda d=dev_id: self.nudge_delay(d, -DELAY_STEP_MS)).grid(row=0, column=0)
        ttk.Scale(dl, from_=0, to=MAX_DELAY_MS, variable=row["delay"], style=f"{st}.Horizontal.TScale",
                  command=lambda v, d=dev_id: self.on_slider(d)).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(dl, text="+", style="Small.TButton", width=2,
                   command=lambda d=dev_id: self.nudge_delay(d, DELAY_STEP_MS)).grid(row=0, column=2)
        tk.Label(c, textvariable=row["delay_text"], font=self.f_body, fg=TEXT, bg=bg).grid(row=8, column=0,
                                                                                            pady=(4, 0))
        row["status_lbl"] = tk.Label(c, textvariable=row["status"], font=self.f_small, fg=MUTED, bg=bg)
        row["status_lbl"].grid(row=9, column=0, pady=(4, 0))
        self.rows[dev_id] = row
        self.sync_output(dev_id, out)

    def restyle_strip(self, dev_id):
        """Light a strip up when its switch is on."""
        row = self.rows[dev_id]
        on = row["enabled"].get()
        bg = STRIP_ON if on else STRIP
        row["outer"].configure(bg=BORDER_ON if on else BORDER)
        stack = [row["card"]]
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if isinstance(w, (tk.Frame, tk.Canvas)) or (isinstance(w, tk.Label) and w["bg"] != CHIP):
                w.configure(bg=bg)
        row["icon"].light(ACCENT if on else None)
        st = "StripOn" if on else "Strip"
        stack = [row["card"]]
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if isinstance(w, ttk.Scale):
                w.configure(style=f"{st}.{'Vertical' if str(w.cget('orient')) == 'vertical' else 'Horizontal'}.TScale")
            elif isinstance(w, ttk.Checkbutton):
                w.configure(style=f"{st}.Switch.TCheckbutton")

    def sync_output(self, dev_id, out=None):
        row = self.rows[dev_id]
        out = out or self.engine.outputs[dev_id]
        out.delay_ms = int(float(row["delay"].get()))
        out.volume = int(float(row["volume"].get())) / 100.0
        row["delay_text"].set(f"Delay  {out.delay_ms} ms")
        row["vol_text"].set(f"{int(out.volume * 100)}%")

    def nudge_delay(self, dev_id, step):
        row = self.rows[dev_id]
        row["delay"].set(max(0, min(MAX_DELAY_MS, int(float(row["delay"].get())) + step)))
        self.on_slider(dev_id)

    def on_slider(self, dev_id):
        self.sync_output(dev_id)
        self.save_settings()

    def on_row_changed(self, dev_id=None):
        if dev_id in self.rows and not self.rows[dev_id]["is_source"]:
            self.restyle_strip(dev_id)
        self.apply_outputs()
        self.save_settings()

    def on_source_changed(self):
        src = self.current_source_id()
        self.save_settings()
        self.build_rows()
        if self.engine.running and src:
            self.engine.start(src)
        self.apply_outputs()
        self.save_settings()

    def on_show_virtual(self):
        self.save_settings()
        self.build_rows()
        self.apply_outputs()

    def on_clicks(self):
        self.engine.sync_clicks = self.clicks_var.get()

    def apply_outputs(self):
        src = self.current_source_id()
        for dev_id, out in self.engine.outputs.items():
            row = self.rows.get(dev_id)
            want = (self.engine.running and row is not None and not row["is_source"]
                    and dev_id != src and row["enabled"].get())
            if want and not out.running:
                out.start()
            elif not want and out.running:
                out.stop()

    # ---------------- start / stop ----------------
    def toggle(self):
        if self.engine.running:
            self.engine.stop()
        else:
            src = self.current_source_id()
            if not src:
                self.status_var.set("Pick where the movie sound comes from first")
                return
            self.engine.start(src)
        self.start_btn.set(self.engine.running)
        self.apply_outputs()

    def tick_meters(self):
        src_level = to_meter(self.engine.level) if self.engine.running else 0.0
        for dev_id, row in self.rows.items():
            if row["is_source"]:
                row["meter"].set(src_level)
            else:
                out = self.engine.outputs.get(dev_id)
                row["meter"].set(to_meter(out.level) if out and out.running else 0.0)
        self.root.after(50, self.tick_meters)

    def tick(self):
        src = self.current_source_id()
        default = self.windows_default_id()
        if self.source_var.get() != AUTO_SOURCE and src and default and src != default:
            self.warn_var.set("⚠  Windows is playing sound on a different device, so this source is probably "
                              "silent. Pick automatic, or switch Windows' output to this device.")
        else:
            self.warn_var.set("")
        for dev_id, row in self.rows.items():
            out = self.engine.outputs.get(dev_id)
            if row["is_source"]:
                continue
            live = bool(out and out.running and out.status == "playing")
            if out and out.running:
                extra = out.safety_ms
                row["status"].set(("● LIVE" + (f" · +{extra} ms anti-crackle" if extra else ""))
                                  if live else out.status)
            elif row["enabled"].get():
                row["status"].set("Ready · press Start")
            else:
                row["status"].set("Off")
            row["status_lbl"].configure(fg=GREEN if live else (RED if out and out.running else MUTED))
        if self.engine.running:
            n = sum(1 for o in self.engine.outputs.values() if o.running)
            ok = self.engine.status == "running"
            self.status_var.set(f"Live · {n} device{'s' if n != 1 else ''}" if ok else self.engine.status)
            self.status_dot.configure(fg=GREEN if ok else RED)
        else:
            self.status_var.set("Stopped")
            self.status_dot.configure(fg=MUTED)
        self.root.after(300, self.tick)

    # ---------------- settings ----------------
    def save_settings(self):
        self.settings["source_name"] = self.source_var.get()
        self.settings["show_virtual"] = bool(self.show_virtual.get())
        for dev_id, row in self.rows.items():
            if row["is_source"]:
                continue   # keep the device's own saved choices for when it isn't the source
            self.settings["devices"][dev_id] = {
                "enabled": bool(row["enabled"].get()),
                "volume": int(float(row["volume"].get())),
                "delay": int(float(row["delay"].get())),
            }
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except OSError:
            pass

    def on_close(self):
        self.save_settings()
        self.engine.stop()
        self.root.destroy()


def already_running():
    """True if another copy of the app is open (two copies would fight over the headphones)."""
    try:
        from ctypes import windll
        windll.kernel32.CreateMutexW(None, False, "MultiHeadphones.SingleInstance")
        return windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)   # sharp text on high-DPI screens
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("MultiHeadphones.App")  # own taskbar icon
    except Exception:
        pass
    if already_running():
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(APP_NAME, "Multi Headphones is already open. Check the taskbar.")
        r.destroy()
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
