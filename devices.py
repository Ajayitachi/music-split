"""Figure out what kind of device each audio output is (Bluetooth, wired, HDMI ...)."""

import subprocess

_PS_SCRIPT = (
    "Get-PnpDevice -Class AudioEndpoint -PresentOnly | ForEach-Object { "
    "$p = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_Parent "
    "-ErrorAction SilentlyContinue).Data; \"$($_.InstanceId)|$p\" }"
)


def device_parents():
    """Map soundcard device id (lower case) -> parent hardware id, via PnP."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return {}
    parents = {}
    prefix = "swd\\mmdevapi\\"
    for line in out.splitlines():
        if "|" not in line:
            continue
        inst, parent = line.split("|", 1)
        inst = inst.strip().lower()
        if inst.startswith(prefix):
            parents[inst[len(prefix):]] = parent.strip().upper()
    return parents


def classify(name, parent):
    """Short label for the device type."""
    n = name.lower()
    p = (parent or "").upper()
    if p.startswith("BTH") or "hands-free" in n or "bluetooth" in n:
        return "Bluetooth"
    if p.startswith("USB"):
        return "Wired (USB)"
    if "hdmi" in n or "display audio" in n or "VEN_10DE" in p or "VEN_1002" in p:
        return "HDMI / monitor"
    if "s/pdif" in n or "spdif" in n or "digital audio" in n:
        return "Digital (S/PDIF)"
    if p.startswith("HDAUDIO"):
        return "Wired (3.5 mm jack)" if "headphone" in n else "PC speakers / 3.5 mm jack"
    return "Other"
