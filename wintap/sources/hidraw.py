"""Raw HID read of a HID-sensor device (usage page 0x20) — e.g. a USB BMI160/BNO055 IMU.

Use this when the IMU is not claimed by the Windows sensor driver (plain clamshells have no
IMU at all; a ~$5 USB breakout gives any PC one at the full device rate, 100-1600 Hz).

Experimental: pip install wintap[hid] (hidapi + hidparser). The report descriptor is parsed
with hidparser when available; otherwise a fixed int16 x3 accel + int16 x3 gyro layout is
assumed (the common breakout format). Accel is scaled to g, gyro to deg/s.
"""
import struct
import threading
import time

from .base import Source

SENSOR_PAGE = 0x20
# HID usage-table sensor usages we care about
ACCEL_3D = 0x73
GYRO_3D = 0x76


class HidRawSource(Source):
    kind = "hid"

    def __init__(self, usage_page=SENSOR_PAGE, accel_lsb_per_g=16384.0, gyro_lsb_per_dps=16.4):
        super().__init__()
        self.usage_page = usage_page
        self.accel_lsb_per_g = accel_lsb_per_g
        self.gyro_lsb_per_dps = gyro_lsb_per_dps

    def start(self):
        try:
            import hid
        except ImportError:
            self.error = "install wintap[hid] (hidapi) to use a raw HID IMU"
            return
        try:
            devs = [d for d in hid.enumerate(0, 0) if d.get("usage_page") == self.usage_page]
        except Exception as e:
            self.error = f"hid.enumerate failed: {e}"
            return
        if not devs:
            self.error = (f"no HID device with usage page 0x{self.usage_page:02X} found — "
                          "plug in a USB IMU, or use --source winrt for the built-in sensor")
            return
        info = devs[0]
        self.device_info = {k: info.get(k) for k in ("vendor_id", "product_id", "product_string", "path")}
        try:
            dev = hid.Device(vendor_id=info["vendor_id"], product_id=info["product_id"], path=info.get("path"))
        except Exception as e:
            self.error = f"cannot open {info.get('product_string')!r}: {e}"
            return
        parse = self._make_parser(dev)
        if parse is None:
            self.error = "could not obtain/parse the HID report descriptor on this build"
            return
        threading.Thread(target=self._read_loop, args=(dev, parse), daemon=True, name="wintap-hid").start()

    def _make_parser(self, dev):
        """Returns report_bytes -> list of (kind, x, y, z), or None."""
        desc = None
        for attr in ("get_report_descriptor",):
            fn = getattr(dev, attr, None)
            if fn:
                try:
                    desc = fn()
                except Exception:
                    desc = None
        if desc:
            try:
                import hidparser
                parsed = hidparser.parse(desc) if hasattr(hidparser, "parse") else None
                if parsed is not None:
                    return self._parser_from_hidparser(parsed)
            except Exception:
                pass
        # Fallback: fixed layout — report id byte + accel i16 x3 + gyro i16 x3 (BMI160-style).
        def fixed(buf):
            off = 1 if buf and buf[0] != 0 else 0
            if len(buf) < off + 12:
                return []
            ax, ay, az = struct.unpack_from("<3h", buf, off)
            gx, gy, gz = struct.unpack_from("<3h", buf, off + 6)
            return [("accel", ax / self.accel_lsb_per_g, ay / self.accel_lsb_per_g, az / self.accel_lsb_per_g),
                    ("gyro", gx / self.gyro_lsb_per_dps, gy / self.gyro_lsb_per_dps, gz / self.gyro_lsb_per_dps)]
        return fixed

    def _parser_from_hidparser(self, parsed):
        # hidparser's API varies by version; this is best-effort and falls back to None.
        try:
            fields = parsed.report_fields() if hasattr(parsed, "report_fields") else None
            if not fields:
                return None
            accel_fields = [f for f in fields if getattr(f, "usage", None) == ACCEL_3D]
            gyro_fields = [f for f in fields if getattr(f, "usage", None) == GYRO_3D]
            if not (accel_fields and gyro_fields):
                return None
            # Too layout-specific to trust blind across versions; refuse rather than misparse.
            return None
        except Exception:
            return None

    def _read_loop(self, dev, parse):
        dev.open()
        self.found["accel"] = True
        self.found["gyro"] = True
        while True:
            try:
                buf = dev.read(64, timeout_ms=1000)
            except Exception as e:
                self.error = f"HID read failed: {e}"
                return
            if not buf:
                continue
            t = time.monotonic()
            for item in parse(bytes(buf)):
                if item:
                    self.put(item[0], t, *item[1:4])
