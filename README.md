# Multi Headphones

Play a movie's sound on several headphones at the same time on Windows:
Bluetooth headphones, wired earphones (3.5 mm jack or USB-C), USB headsets and speakers, all mixed together.

## Start
Double-click **`Start Multi Headphones.bat`**.

## Use
1. Connect every headphone/earphone to the PC (pair Bluetooth ones in Windows Settings, plug in wired ones).
2. **Movie sound comes from**: the device Windows plays on (normally already selected).
   That device keeps the original sound. Every device you tick gets a copy.
3. Tick the other headphones/earphones and press **Start**.
4. Play the movie in any player or browser.

### Getting everyone in sync
- Bluetooth is slower than wired, so wired earphones will hear sound a little earlier.
  Raise the **Delay** of the faster device until everyone hears the same moment.
- **Sync test** beeps once a second: wear one earbud from each of two devices and move the slider
  until the beeps line up.
- For perfect sync, set Windows' output to a device nobody listens to (Digital Audio S/PDIF, or a
  monitor with its speakers turned down), choose it as the source, and tick *all* headphones.
- If the sound is behind the picture, use the player's audio-delay setting (VLC: `J` / `K`).

Settings (ticks, volume, delay) are remembered in `settings.json`.
If a Bluetooth headphone is switched off and on again, it reconnects by itself.

## Limits
- Many built-in Bluetooth adapters can stream to only 2–3 Bluetooth headphones at once before stuttering.
  A second USB Bluetooth dongle helps.
- Audio only flows while the tool is open.
