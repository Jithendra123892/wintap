"""Windows platform adapter with the same interface as the LidTap prototype's macOS
sensors module, so detector.py / app.py run unchanged.

- now() / seconds_since_input(): monotonic clock + low-level input hooks (inputmon.py).
- listen_access(): low-level hooks need no special permission on Windows -> "granted".
- Sensors wraps a pluggable source (sources/) and exposes .samples / .lid_angle / .found /
  .error. Lid open/closed (the only lid signal Windows gives) is mapped to 130/0 degrees so
  the detector's "lid moved >= 2 deg" gate works unchanged.
"""
import time

from . import inputmon
from .sources import make_source


def now():
    """Monotonic seconds — the same clock the sources timestamp samples with."""
    return time.monotonic()


def seconds_since_input():
    """Seconds since the last typing / click / scroll anywhere on the system."""
    return inputmon.seconds_since_input()


def listen_access():
    return "granted"


def request_listen_access():
    return True


class Sensors:
    def __init__(self, source=None):
        self._source = source if source is not None else make_source("auto")
        self.samples = self._source.samples
        self.found = self._source.found
        self._lid = inputmon.LidState()
        self.on_sample = None  # optional tap for recording: fn(kind, t, x, y, z)
        _orig_put = self._source.put

        def put(kind, t, x, y, z):
            _orig_put(kind, t, x, y, z)
            cb = self.on_sample
            if cb is not None:
                cb(kind, t, x, y, z)

        self._source.put = put

    @property
    def error(self):
        return self._source.error

    @property
    def lid_angle(self):
        return self._lid.angle

    def start(self):
        inputmon.start()
        try:
            self._source.start()
        except Exception as e:  # keep the app alive and show the reason
            self._source.error = f"{type(e).__name__}: {e}"
