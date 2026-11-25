# Multi Headphones

Play a movie's sound on **several headphones at the same time** on a Windows PC: Bluetooth headphones,
wired earphones (3.5 mm jack or USB-C), USB headsets and speakers, all together. Each device gets its own
volume and sync delay.

![Multi Headphones](assets/icon.png)

---

## Install

**No Python and no admin rights needed.**

1. Open the **[Releases](https://github.com/Ajayitachi/music-split/releases/latest)** page of this repo and download **`MultiHeadphones-Windows.zip`**.
2. Right-click the zip → **Extract All…**
3. Open the extracted folder and double-click **`Install.bat`**.
4. **Multi Headphones** opens, and is added to the **Start Menu** and the **Desktop**.

> **"Windows protected your PC"?** The app isn't code-signed, so Windows warns about it the first time.
> Click **More info → Run anyway**.

**Uninstall:** *Settings → Apps → Installed apps → Multi Headphones → Uninstall*.
Your saved settings stay in `%APPDATA%\Multi Headphones` (delete that folder to remove them too).

---

## How to use

1. **Connect your headphones.**
   - Bluetooth: pair them in *Windows Settings → Bluetooth & devices*.
   - Wired: plug them into the headphone jack or a USB-C port.
2. **Open Multi Headphones.** Every connected device appears as a channel strip.
3. **Movie sound comes from**: leave it on **Windows default output (automatic)**.
   The device Windows plays on gets the purple **SOURCE** strip. It plays the movie directly.
4. **Switch on** every other headphone that should play (the switch at the top of each strip turns blue).
5. Press **START**.
6. Play the movie in any player or browser. Every switched-on device now plays it too.

| On each strip | What it does |
|---|---|
| Switch | Turn this device on or off |
| Vertical fader | Volume for this device (0–150 %) |
| LED meter | Shows the sound this device is getting |
| Delay − / + | Makes this device play later, to line it up with the others (10 ms steps) |
| ● LIVE | Playing. "+20 ms anti-crackle" means the app made the buffer bigger by itself to stop crackling |

Other controls: **Virtual devices** shows software outputs (Steam, voice changers…), which are hidden by default.
**Sync beep** plays a beep every second on all devices. The ⟳ button refreshes the device list.

### Getting everyone in sync
- Bluetooth is always a little behind wired earphones.
- Turn on **Sync beep**, wear one earbud from two devices, and press **Delay +** on the device that beeps
  *first* until both beep together.
- The SOURCE device can't be delayed. For perfect sync, set Windows' output to a device nobody listens to
  (for example the laptop speakers with the volume down), pick that as the source, and switch on *all*
  headphones. Then every headphone gets its own Delay.
- If the sound is behind the picture, use the player's audio delay (VLC: `J` / `K`).

---

## Troubleshooting

| Problem | Try this |
|---|---|
| A wired earphone is silent | If it's the **SOURCE**, it plays whatever Windows plays. Check its volume in Windows. |
| A device is missing | Press ⟳. Bluetooth: make sure it shows **Connected** in Windows Settings. |
| Crackling / "chirr" noise with many devices | See *Known issues* below. Try fewer devices at once and keep the PC free of heavy work. |
| Bluetooth sounds tinny or crackly | Close apps that use the Bluetooth headset's **microphone** (calls, Discord, voice changers): Windows then switches the buds to low-quality "call" mode. |
| Bluetooth stutters | Wi-Fi and Bluetooth share one radio on many laptops. Move closer, or use a USB Bluetooth dongle. |

## Known issues
- **Crackling with 4 devices at once** (1 Bluetooth + 2 wired + speakers) has been reported and is still being
  investigated. Up to 3 devices work cleanly in testing.
- Many built-in Bluetooth adapters handle only 2–3 Bluetooth headphones at once.
- Sound only flows while the app is open.

---

## For developers

**Run from source:** install Python 3.12+, then double-click **`Start Multi Headphones.bat`**
(first run creates `.venv` and installs `soundcard`, `numpy`, `sv-ttk`).

**Build the installer zip:** double-click **`build.bat`**. It makes `dist\MultiHeadphones\MultiHeadphones.exe`
and `dist\MultiHeadphones-Windows.zip` with PyInstaller.

**Test:** `.venv\Scripts\python.exe tests\self_test.py` plays a short tone on the default output and checks
that every other output gets it.

| File | What |
|---|---|
| `multi_headphones.py` | The app window (mixer-style UI, settings) |
| `audio_engine.py` | Captures the source with WASAPI loopback and copies it to every output; self-adjusting buffers |
| `devices.py` | Detects device type (Bluetooth / USB / 3.5 mm / HDMI / virtual) |
| `installer/` | `Install.bat`, `install.ps1`, `uninstall.ps1` (per-user install, Start Menu + Desktop shortcuts) |
| `MultiHeadphones.spec`, `build.bat` | PyInstaller build |
| `tools/make_icon.py` | Draws `assets/icon.ico` |
