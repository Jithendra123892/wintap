"""Physics-simulated laptop, for demos and tests on machines without an IMU.

A lid tap twists the chassis about the hinge: a damped ~40 Hz oscillation on the gyro
(5-12 deg/s peak against ~0.15 deg/s per-axis idle noise) plus a short accel shake.
Left/right zones flip the sign of the off-hinge twist axis; top/bottom zones change the
shake amplitude (hence the gyro/accel ratio) — the same cues the real detector uses.
Desk bumps are accel-dominated with a small gyro kick, so they cross the trigger but are
labelled noise during calibration of negatives.
"""
import math
import queue
import random
import threading
import time

from .base import Source


class SyntheticSource(Source):
    kind = "synthetic"

    def __init__(self, fs=800.0, seed=1, realtime=True):
        super().__init__()
        self.fs = float(fs)
        self.realtime = realtime
        self.rng = random.Random(seed)
        self._req = queue.SimpleQueue()
        self._bumps = True
        self._stop = threading.Event()
        self.tap_count = 0

    def request_tap(self, zone, rows, cols):
        self._req.put((int(zone), int(rows), int(cols)))

    def set_bumps(self, on):
        self._bumps = bool(on)

    def stop(self):
        self._stop.set()

    def start(self):
        self.found["accel"] = True
        self.found["gyro"] = True
        threading.Thread(target=self._run, daemon=True, name="wintap-synthetic").start()

    # -- signal generation ------------------------------------------------------------------

    def _noise(self):
        g = [self.rng.gauss(0.0, 0.15) for _ in range(3)]
        a = [self.rng.gauss(0.0, 0.004) for _ in range(2)] + [1.0 + self.rng.gauss(0.0, 0.004)]
        return g, a

    def _bump(self):
        amp_a = self.rng.uniform(0.3, 0.7)
        amp_g = self.rng.uniform(2.8, 4.2)  # above the ~1.5 deg/s trigger, well below a tap
        f = self.rng.uniform(25.0, 40.0)
        tau = self.rng.uniform(0.02, 0.035)
        d = [self.rng.uniform(-1, 1) for _ in range(3)]
        nrm = math.sqrt(sum(v * v for v in d)) or 1.0
        d = [v / nrm for v in d]
        for i in range(int(0.12 * self.fs)):
            x = i / self.fs
            e = math.exp(-x / tau)
            s = amp_g * e * math.sin(2 * math.pi * f * x)
            g = [s * v for v in d]
            a = [amp_a * e * math.sin(2 * math.pi * f * x) + self.rng.gauss(0, 0.004),
                 self.rng.gauss(0, 0.004),
                 1.0 + self.rng.gauss(0, 0.004)]
            yield g, a

    def _tap(self, zone, rows, cols):
        r, c = divmod(zone, cols)
        lr = 1.0 if c >= cols / 2 else -1.0
        tb = 1.0 if r >= rows / 2 else -1.0
        A = self.rng.uniform(5.0, 12.0)          # deg/s peak twist
        f = self.rng.uniform(38.0, 52.0)
        tau = self.rng.uniform(0.025, 0.04)
        shake = self.rng.uniform(0.25, 0.40) if tb > 0 else self.rng.uniform(0.04, 0.12)  # g, disjoint per row
        for i in range(int(0.25 * self.fs)):
            x = i / self.fs
            e = math.exp(-x / tau)
            gx = 0.55 * lr * A * math.exp(-x / (tau * 0.6)) * math.sin(2 * math.pi * f * 1.3 * x)
            gy = A * e * math.sin(2 * math.pi * f * x)
            gz = self.rng.uniform(-0.2, 0.2) * A * e
            g = [gx + self.rng.gauss(0, 0.15), gy + self.rng.gauss(0, 0.15), gz + self.rng.gauss(0, 0.15)]
            ax = shake * math.exp(-x / 0.012) * math.cos(2 * math.pi * f * x)
            a = [ax + self.rng.gauss(0, 0.004), self.rng.gauss(0, 0.004),
                 1.0 + shake * 0.5 * math.exp(-x / 0.02) + self.rng.gauss(0, 0.004)]
            yield g, a

    # -- producer loop ------------------------------------------------------------------------

    def _run(self):
        t = time.monotonic()
        dt = 1.0 / self.fs
        while not self._stop.is_set():
            req = None
            try:
                req = self._req.get(timeout=dt * 8 if self.realtime else 0.001)
            except queue.Empty:
                pass
            for _ in range(max(1, int(0.05 * self.fs))):  # 50 ms of idle noise
                g, a = self._noise()
                self.put("gyro", t, *g)
                self.put("accel", t, *a)
                t += dt
                if self.realtime:
                    time.sleep(dt)
            if req is not None:
                zone, rows, cols = req
                for g, a in self._tap(zone, rows, cols):
                    self.put("gyro", t, *g)
                    self.put("accel", t, *a)
                    t += dt
                    if self.realtime:
                        time.sleep(dt)
                self.tap_count += 1
            elif self._bumps and self.rng.random() < (0.35 if self.realtime else 0.06):
                for g, a in self._bump():
                    self.put("gyro", t, *g)
                    self.put("accel", t, *a)
                    t += dt
                    if self.realtime:
                        time.sleep(dt)
