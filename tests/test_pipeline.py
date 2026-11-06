"""End-to-end pipeline tests on the synthetic laptop: calibrate -> noise -> train -> live.

Runs the real Detector thread and App against SyntheticSource at 800 Hz and 200 Hz
(the rates of a raw-HID IMU and a typical WinRT sensor), entirely hardware-free.
"""
import math
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from wintap import features, model
from wintap.app import App
from wintap.detector import FS, N
from wintap.features import N_FEATURES
from wintap.sources.synthetic import SyntheticSource


def drive_calibration(app, src, rows, cols, timeout=60):
    """Feed one synthetic tap per pending calibration slot until done.

    Re-requests the current slot if it has not advanced for a while (a tap can fall
    inside the detector's 1 s warm-up window or be gated)."""
    last_pos = -1
    last_change = time.monotonic()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = app.status()
        if st["mode"] != "calibrate":
            return True
        c = st["calib"]
        if c["pos"] != last_pos:
            last_pos = c["pos"]
            last_change = time.monotonic()
            src.request_tap(model.zone_index(c["target"]), rows, cols)
        elif time.monotonic() - last_change > 1.5:
            last_change = time.monotonic()
            src.request_tap(model.zone_index(c["target"]), rows, cols)
        time.sleep(0.005)
    return False


class FeatureTests(unittest.TestCase):
    def test_feature_vector_shape(self):
        self.assertEqual(N_FEATURES, 70)
        rng = np.random.default_rng(0)
        g = rng.normal(0, 1, (N, 3))
        a = rng.normal(0, 0.1, (N, 3))
        f = features.extract(g, a)
        self.assertEqual(f.shape, (N_FEATURES,))
        self.assertTrue(np.all(np.isfinite(f)))

    def test_highpass_removes_dc(self):
        from wintap.detector import HighPass3
        hp = HighPass3()
        for _ in range(2000):
            out = hp(1.0, 2.0, 3.0)  # constant gravity-like signal
        self.assertAlmostEqual(float(np.linalg.norm(out)), 0.0, places=3)


class PipelineTests(unittest.TestCase):
    def _run_session(self, fs, seed=42):
        tmp = tempfile.TemporaryDirectory()
        src = SyntheticSource(fs=fs, realtime=False, seed=seed)
        app = App(Path(tmp.name) / "data", source=src)
        app.start()
        src.set_bumps(False)
        app.calibrate_start({"rows": 2, "cols": 2, "per_zone": 12, "block": 2})
        self.assertTrue(drive_calibration(app, src, 2, 2), "calibration did not finish")
        # noise examples: simulated desk bumps, collected by COUNT (fast-forward speed
        # is machine-dependent, so wall-clock windows record a variable number)
        app.negatives_start({"seconds": 90})
        src.set_bumps(True)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            n_noise = sum(1 for s in app.samples if s["label"] == "noise")
            if n_noise >= 10 or app.status()["mode"] != "negatives":
                break
            time.sleep(0.05)
        src.set_bumps(False)
        app.stop()
        report = app.train()
        # live: 2 fresh taps per zone, measured against their true label.
        # Request the next tap only after the previous one produced a prediction,
        # so taps never merge inside the detector's refractory window (sensor time
        # runs faster than wall time in fast-forward mode).
        last = max((e["id"] for e in app.events), default=0)
        expected = []
        for z in range(4):
            for _ in range(2):
                src.request_tap(z, 2, 2)
                expected.append(f"z{z}")
                t_end = time.monotonic() + 15
                while time.monotonic() < t_end:
                    if len([e for e in app.events_since(last) if "pred" in e]) >= len(expected):
                        break
                    time.sleep(0.02)
        deadline = time.monotonic() + 30
        evs = []
        while time.monotonic() < deadline:
            evs = [e for e in app.events_since(last) if "pred" in e]
            if len(evs) >= len(expected):
                break
            time.sleep(0.05)
        evs = [e for e in app.events_since(last) if "pred" in e]
        tmp.cleanup()
        return report, list(zip(expected, evs))

    def test_end_to_end_800hz(self):
        report, live = self._run_session(800)
        accs = [r["acc"]["Full grid"] for r in report["models"] if r["acc"]["Full grid"] is not None]
        self.assertTrue(accs, "no model could cross-validate")
        self.assertGreaterEqual(max(accs), 0.7, f"CV accuracy too low at 800 Hz: {accs}")
        self.assertGreaterEqual(len(live), 6, f"too few live predictions: {len(live)}")
        ok = sum(1 for want, ev in live if not ev["pred"]["rejected"] and ev["pred"]["label"] == want)
        self.assertGreaterEqual(ok / len(live), 0.7,
                                f"live accuracy too low: {[(w, e['pred']) for w, e in live]}")

    def test_end_to_end_200hz(self):
        # WinRT sensors typically deliver 60-100 Hz; 200 Hz is the pessimistic bound here.
        report, live = self._run_session(200, seed=7)
        accs = [r["acc"]["Full grid"] for r in report["models"] if r["acc"]["Full grid"] is not None]
        self.assertTrue(accs, "no model could cross-validate")
        self.assertGreaterEqual(max(accs), 0.6, f"CV accuracy too low at 200 Hz: {accs}")
        ok = sum(1 for want, ev in live if not ev["pred"]["rejected"] and ev["pred"]["label"] == want)
        self.assertGreaterEqual(ok / max(len(live), 1), 0.6,
                                f"live accuracy too low at 200 Hz: {[(w, e['pred']) for w, e in live]}")

    def test_noise_bump_is_rejected(self):
        tmp = tempfile.TemporaryDirectory()
        src = SyntheticSource(fs=800, realtime=False, seed=3)
        app = App(Path(tmp.name) / "data", source=src)
        app.start()
        src.set_bumps(False)
        app.calibrate_start({"rows": 2, "cols": 2, "per_zone": 8, "block": 2})
        self.assertTrue(drive_calibration(app, src, 2, 2))
        # collect negatives by COUNT, not wall time: in fast-forward mode the number of
        # bumps recorded per wall second depends on machine speed (CI runners differ)
        app.negatives_start({"seconds": 90})
        src.set_bumps(True)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            n_noise = sum(1 for s in app.samples if s["label"] == "noise")
            if n_noise >= 10 or app.status()["mode"] != "negatives":
                break
            time.sleep(0.05)
        src.set_bumps(False)
        app.stop()
        self.assertGreaterEqual(sum(1 for s in app.samples if s["label"] == "noise"), 10,
                                "too few noise examples recorded")
        app.train()
        m = app.model
        self.assertIsNotNone(m)
        # a fresh desk bump: modest gyro, accel-dominated (taps are gyro-dominated) ->
        # must classify as noise or be open-set rejected
        g = np.zeros((N, 3))
        a = np.zeros((N, 3))
        for i in range(N):
            x = i / FS
            if x < 0.12:
                e = math.exp(-x / 0.03)
                g[i] = [1.1 * e * math.sin(2 * math.pi * 30.0 * x)] * 3
                a[i] = [0.6 * e, 0.0, 0.5 * e]
        pred = m.predict(features.extract(g, a), reject_factor=2.0)
        self.assertTrue(pred["rejected"] or pred["label"] == model.NOISE, pred)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
