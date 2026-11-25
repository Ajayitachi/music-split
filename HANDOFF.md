# Handoff: Multi Headphones project

> **New chat?** Start with: *"Read HANDOFF.md and README.md in this repo, then help me continue."*

Last updated: 2026-11-25 (worked on the office PC).

## Goal
Watch a movie on a Windows PC and hear the sound on **several headphones at once**:
Bluetooth headphones/earbuds **and** wired earphones (3.5 mm jack or USB-C), each with its own
volume and sync delay. (Phones can't do this from a normal app, so we chose a Windows PC tool.)

## How it works
- **Source** = the device Windows plays the movie on (default: "Windows default output (automatic)",
  which follows Windows when the default output changes).
- The source's sound is captured with **WASAPI loopback** and copied to every ticked output.
- Each output has its own queue, **delay slider** (0–600 ms) and **volume** (0–150 %).
  A drift controller keeps each device at its delay (drops/inserts 1 frame per 10 ms block).
- The source device itself plays the original sound; the tool never copies to it (avoids echo).
- **Sync test** button: beep every second through all outputs, to line up delays by ear.
- Devices that unplug/disconnect are retried every 2 s and resume automatically.
- Device list refreshes every 3 s. Device type (Bluetooth / Wired USB / 3.5 mm / HDMI / S/PDIF)
  comes from the PnP parent of each audio endpoint (`devices.py`, via PowerShell).

## Files
| File | What |
|---|---|
| `multi_headphones.py` | Tkinter GUI (source picker, device rows, Start/Stop, Sync test, settings) |
| `audio_engine.py` | Capture + fan-out engine (`Engine`, `Output`), exact device-id lookup |
| `devices.py` | Classifies outputs as Bluetooth / Wired / HDMI / S/PDIF |
| `Start Multi Headphones.bat` | Double-click launcher; creates `.venv` + installs deps on first run |
| `requirements.txt` | `soundcard`, `numpy` |
| `tests/self_test.py` | End-to-end test: plays a tone on the default output, checks every other output receives it |
| `settings.json` | Per-PC saved ticks/delays/volumes (**not committed**, device IDs differ per PC) |

## Setup on a new PC
1. Install Python 3.12+ from python.org (tick "Add python.exe to PATH").
2. `git clone` this repo, then double-click **Start Multi Headphones.bat**.
3. Optional test: `.venv\Scripts\python.exe tests\self_test.py` (plays a short tone).

## Status
**Working and tested (office PC):**
- GUI opens/closes cleanly; Start/Stop; settings saved.
- Full end-to-end test passed: movie sound on Windows default → copied to all other outputs
  (wired USB Bassheads, LG monitor HDMI, S/PDIF).
- Bluetooth output worked once (OnePlus Nord Buds 3 Pro received beeps together with wired Bassheads).
- Source auto-follows Windows default; red warning if a manual source isn't the Windows default.

**Open issue (in progress when we stopped):**
- After the PC restart, the **OnePlus Nord Buds 3 Pro** Bluetooth link connected but the
  **stereo audio endpoint never came up** ("Headphones (OnePlus…)" stayed not-present), so they kept
  "disconnecting" from the app's point of view. We **removed the old pairing**; next step was to
  re-pair fresh (phone Bluetooth OFF, case button ~3 s until white blink, Add device → Bluetooth)
  and re-run the test. If it still drops: attach the motherboard Wi-Fi/BT **antennas**, and keep
  the phone from grabbing the buds (they support dual connection).
- **Boult earbuds ("SHK BOULTT")** are not paired yet. The PC only saw their Bluetooth LE signal; one
  pairing attempt failed authentication. Needs: forget on phone, phone BT off, reset/pairing mode.

## Office PC findings (hardware-specific, may not apply at home)
- Motherboard **Gigabyte Z790 D AX**: Realtek ALC897 audio, Realtek **8852CE** Wi-Fi 6E + Bluetooth.
- Bluetooth radio was **switched off** and on Microsoft's generic driver → scans found nothing.
  Fixed by installing Gigabyte's **Realtek 8852 Bluetooth driver 18.4032.2510.0900** and
  **Realtek 8852 WIFI driver 6001.16.172.0**, then turning the radio on.
- Turned **off** "Allow the computer to turn off this device to save power" on the Bluetooth adapter.
- 3.5 mm jack: onboard audio uses Microsoft's generic HD Audio driver; the jack output only appears
  when earphones are in the **green / headphone** jack (pink = mic). Realtek Audio Console can make
  front and rear jacks separate devices ("play two different audio streams simultaneously").

## Ideas / next steps
- Package as a single `.exe` (PyInstaller) so other PCs don't need Python.
- Auto sync calibration (measure each device's latency instead of tuning by ear).
- Show a per-device level meter; tray icon; start minimized.
