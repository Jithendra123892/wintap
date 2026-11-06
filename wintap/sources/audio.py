"""Acoustic source: lid-knock detection from the built-in microphone.

For machines whose IMU is not exposed to Windows (most plain clamshells), a tap on
the lid is clearly audible. This source captures the default input (or Stereo Mix
loopback with loopback=True), computes high-frequency band energy per 10 ms block,
and emits pseudo-IMU rows at 800 Hz on the same queue the detector consumes:

  gyro  = knock energy, normalised so idle noise sits at ~0.5 deg/s (the detector's
          adaptive threshold then needs ~6x above noise, exactly like a real IMU)
  gyro.x sign = left/right from the mic-array channel energy difference (DOA)
  accel = knock energy / 8 (g)

Because rows have the same (kind, t, x, y, z) shape, the whole pipeline - adaptive
trigger, 200 ms window, 70 features, per-user model, zone actions - runs unchanged.
Zone resolution is coarser than IMU: left/right is reliable via DOA; top/bottom is
not, so use a 1xN grid. `request_tap` plays a synthetic knock through the speakers
(used by tests and `wintap demo --source audio`), panned by zone column.
"""
import math
import queue
import threading
import time

from .base import Source

FS_OUT = 800  # rows per second emitted to the detector


class AudioSource(Source):
    kind = "audio"

    def __init__(self, fs=None, device=None, loopback=False, block_s=0.01, live=None):
        super().__init__()
        self.fs = fs  # None -> device default sample rate
        self.device = device
        self.loopback = loopback
        self.block_s = block_s
        self.live = live  # None = auto; False = no hardware, tests inject blocks via _blocks
        self._stop = threading.Event()
        self._blocks = queue.SimpleQueue()  # (el, er) high-freq energies per block
        self._req = queue.SimpleQueue()     # "tap"/("zone", rows, cols) or "bump"
        self._bumps = False
        self._stream = None
        self._out = None
        self._rng = __import__("random").Random(0)

    # -- capture ---------------------------------------------------------------------

    def _cb(self, indata, frames, tinfo, status):
        import numpy as np
        x = indata[:, 0] if indata.ndim > 1 else indata
        y = indata[:, 1] if indata.ndim > 1 else indata
        # high-frequency energy: first difference emphasizes the knock band (~1-6 kHz)
        dl = np.diff(x) if len(x) > 1 else x
        dr = np.diff(y) if len(y) > 1 else y
        self._blocks.put((float(np.mean(dl * dl)) + 1e-12, float(np.mean(dr * dr)) + 1e-12))

    def start(self):
        self.found["accel"] = True
        self.found["gyro"] = True
        self._live = bool(self.live) if self.live is not None else False
        if self.live is None:
            # auto: open hardware if possible
            try:
                import sounddevice as sd  # noqa: F401
                self._live = True
            except ImportError:
                self._live = False
        if not self._live:
            self._fs = self.fs or 16000
            self.block = max(16, int(self._fs * self.block_s))
            threading.Thread(target=self._run, daemon=True, name="wintap-audio").start()
            return
        try:
            import sounddevice as sd
            import numpy as np  # noqa: F401
        except ImportError:
            self.error = "install wintap[audio] (sounddevice) for mic knock detection"
            return
        dev = self.device
        if dev is None:
            if self.loopback:
                dev = next((i for i, d in enumerate(sd.query_devices())
                            if d["max_input_channels"] > 0
                            and ("stereo mix" in d["name"].lower() or "mix" in d["name"].lower())),
                           None)
            if dev is None:
                dev = sd.default.device[0]
        fs = self.fs or float(sd.query_devices(dev)["default_samplerate"])
        self.block = max(16, int(fs * self.block_s))
        try:
            self._stream = sd.InputStream(samplerate=fs, channels=2, device=dev,
                                          blocksize=self.block, callback=self._cb)
            self._stream.start()
        except Exception as e:
            self.error = f"cannot open audio input (device={dev}): {e}"
            return
        self._fs = fs
        threading.Thread(target=self._run, daemon=True, name="wintap-audio").start()

    # -- playback (tests / demo) -------------------------------------------------------

    def _play(self, pan, freq=2500.0, dur=0.12, gain=0.5):
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            return
        if self._out is None:
            self._out = sd.OutputStream(samplerate=self._fs, channels=2)
            self._out.start()
        n = int(self._fs * dur)
        t = np.arange(n) / self._fs
        env = np.exp(-t / 0.03)
        sig = (gain * env * (np.sin(2 * math.pi * freq * t) + 0.3 * np.random.default_rng(1).standard_normal(n))).astype(np.float32)
        gl = 1.0 if pan < 0 else 0.25   # pan -1 = left speaker loud
        gr = 1.0 if pan >= 0 else 0.25
        self._out.write(np.column_stack([sig * gl, sig * gr]))

    def request_tap(self, zone, rows, cols):
        self._req.put(("tap", zone, rows, cols))

    def set_bumps(self, on):
        self._bumps = bool(on)

    # -- producer ----------------------------------------------------------------------

    def _run(self):
        import numpy as np  # noqa: F401
        hist = []  # recent block energies for the adaptive noise floor
        t = time.monotonic()
        dt_out = 1.0 / FS_OUT
        rows_per_block = max(1, int(FS_OUT * self.block / self._fs))
        self._inject = None
        while not self._stop.is_set():
            self.throttle()
            try:
                el, er = self._blocks.get(timeout=0.005)
            except queue.Empty:
                # still emit idle noise rows so the detector's rate/noise tracking works
                el = er = 1e-9
            e = 0.5 * (el + er)
            hist.append(e)
            if len(hist) > 40:  # 0.4 s floor: sustained noise (typing) raises it, impulsive knocks still spike
                hist.pop(0)
            med = sorted(hist)[len(hist) // 2] if hist else 1e-9
            accel_div = 8.0
            if self._inject is not None:
                inj = self._inject
                knock = inj["knock"]
                # stochastic like real taps: amplitude and pan jitter per knock
                amp = (400.0 if knock else 49.0) * self._rng.uniform(0.9, 1.1)
                pan = max(-1.0, min(1.0, inj["pan"] + self._rng.uniform(-0.05, 0.05)))
                e = med * amp                          # knock ~10 deg/s, bump ~3.5 deg/s
                el = e * (1 - pan) / 2 + 1e-12          # pan -1 = left -> lr negative
                er = e * (1 + pan) / 2 + 1e-12
                if not knock:
                    accel_div = 2.0                     # bumps are accel-dominated
                inj["left"] -= 1
                if inj["left"] <= 0:
                    self._inject = None
            mag = math.sqrt(e) / (math.sqrt(med) + 1e-9) * 0.5  # noise ~0.5 deg/s
            lr = (er - el) / (el + er + 1e-12)  # -1 = left knock (left mic channel louder), +1 = right
            for _ in range(rows_per_block):
                t += dt_out
                self.put("gyro", t, lr * 0.55 * mag, mag, 0.05 * mag)
                self.put("accel", t, mag / accel_div, 0.0, 1.0 + mag / 20.0)
            # serve queued synthetic knocks / bumps
            try:
                req = self._req.get_nowait()
            except queue.Empty:
                req = None
            if req is not None:
                _, zone, rows, cols = req
                c = zone % cols
                pan = -1.0 if c < cols / 2 else 1.0
                if self._live:
                    self._play(pan=pan)
                else:
                    self._inject = {"pan": pan, "left": 12, "knock": True}
            elif self._bumps and self._rng.random() < 0.002:
                if self._live:
                    self._play(pan=self._rng.uniform(-1, 1), freq=300.0, dur=0.1, gain=0.15)
                else:
                    self._inject = {"pan": self._rng.uniform(-1, 1), "left": 10, "knock": False}

    def stop(self):
        self._stop.set()
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
            if self._out:
                self._out.stop()
                self._out.close()
        except Exception:
            pass
