"""Source registry: make_source("auto"|"winrt"|"hid"|"synthetic"|"replay:FILE")."""
from .base import Source


def winrt_sensor_present():
    try:
        import winsdk.windows.devices.sensors as s
        return s.Accelerometer.get_default() is not None or s.Gyrometer.get_default() is not None
    except Exception:
        return False


def hid_sensor_present():
    try:
        import hid
        return any(d.get("usage_page") == 0x20 for d in hid.enumerate(0, 0))
    except Exception:
        return False


def audio_input_present():
    try:
        import sounddevice as sd
        return any(d["max_input_channels"] > 0 for d in sd.query_devices())
    except Exception:
        return False


def list_sources():
    return {"winrt_sensor": winrt_sensor_present(), "hid_sensor": hid_sensor_present(),
            "audio_mic": audio_input_present()}


def make_source(name="auto", **kw):
    if name == "auto":
        if winrt_sensor_present():
            name = "winrt"
        elif hid_sensor_present():
            name = "hid"
        elif audio_input_present():
            name = "audio"  # no IMU exposed: fall back to mic knock detection
        else:
            name = "winrt"  # starts fine and reports a clear "no IMU" error in the UI
    if name == "winrt":
        from .winrt import WinRTSource
        return WinRTSource(**kw)
    if name == "hid":
        from .hidraw import HidRawSource
        return HidRawSource(**kw)
    if name == "audio":
        from .audio import AudioSource
        kw.setdefault("loopback", False)
        return AudioSource(**kw)
    if name == "synthetic":
        from .synthetic import SyntheticSource
        return SyntheticSource(**kw)
    if name.startswith("replay:"):
        from .replay import ReplaySource
        return ReplaySource(name.split(":", 1)[1], **kw)
    raise ValueError(f"unknown source {name!r}: auto|winrt|hid|audio|synthetic|replay:FILE")
