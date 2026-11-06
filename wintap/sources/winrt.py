"""Built-in IMU via Windows.Devices.Sensors (WinRT).

Works on machines whose IMU is exposed through the HID sensor class and the Windows sensor
stack: 2-in-1s, convertibles, tablets, and modern-standby laptops. Plain clamshells without
a motion sensor report none (Accelerometer.get_default() -> None) and this source says so.

Units already match the detector: accelerometer in g, gyrometer in deg/s. The report interval
is set to max(minimum_report_interval, requested); typical minimums are 12.5-16 ms
(60-80 Hz). For the full device rate (up to ~1600 Hz on Bosch/STM parts) use the raw-HID
source instead.
"""
import threading
import time

from .base import Source


class WinRTSource(Source):
    kind = "winrt"

    def __init__(self, report_interval_ms=12):
        super().__init__()
        self._interval = int(report_interval_ms)
        self._keep = []

    def start(self):
        try:
            import winsdk.windows.devices.sensors as s
        except ImportError:
            self.error = "winsdk not installed — run: pip install wintap[winrt]"
            return
        try:
            acc = s.Accelerometer.get_default()
            gyr = s.Gyrometer.get_default()
        except Exception as e:
            self.error = f"WinRT sensor init failed: {e}"
            return
        for kind, dev in (("accel", acc), ("gyro", gyr)):
            if dev is None:
                continue
            try:
                dev.report_interval = max(dev.minimum_report_interval, self._interval)
            except Exception:
                pass

            def handler(sender, args, kind=kind):
                r = args.reading
                if kind == "accel":
                    self.put(kind, time.monotonic(), r.acceleration_x, r.acceleration_y, r.acceleration_z)
                else:
                    self.put(kind, time.monotonic(), r.angular_velocity_x, r.angular_velocity_y, r.angular_velocity_z)

            dev.add_reading_changed(handler)
            self._keep.append((dev, handler))
            self.found[kind] = True
        if not (self.found["accel"] or self.found["gyro"]):
            self.error = ("no accelerometer/gyroscope exposed by Windows on this machine "
                          "(common on plain clamshells). Options: pip install wintap[hid] and plug in a "
                          "USB IMU, or run `wintap demo` to see the pipeline on a simulated laptop.")
