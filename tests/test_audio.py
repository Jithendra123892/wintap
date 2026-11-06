"""Full pipeline over the acoustic source (live=False: synthetic blocks are injected
into the producer instead of opening a mic, so this runs on any machine incl. CI).

Knocks are injected panned left/right per zone column; the mic-array channel energy
difference drives the pseudo-gyro x sign, so a 1x2 grid must classify L vs R.
"""
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path

threading.excepthook = lambda a: (print("THREAD DIED:", a.thread.name if a.thread else "?"),
                                  traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback))

from wintap.app import App
from wintap.sources.audio import AudioSource
from test_pipeline import drive_calibration


class AudioPipelineTests(unittest.TestCase):
    def test_audio_pipeline_left_right(self):
        tmp = tempfile.TemporaryDirectory()
        src = AudioSource(live=False)
        app = App(Path(tmp.name) / "data", source=src)
        app.start()
        app.set_config({"gating": False})  # input hooks are unreliable on headless/VM boxes; gating is a user toggle
        self.assertIsNone(src.error)
        app.calibrate_start({"rows": 1, "cols": 2, "per_zone": 6, "block": 2})
        self.assertTrue(drive_calibration(app, src, 1, 2, timeout=180), "calibration did not finish")
        app.negatives_start({"seconds": 90})
        src.set_bumps(True)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            n_noise = sum(1 for s in app.samples if s["label"] == "noise")
            if n_noise >= 8 or app.status()["mode"] != "negatives":
                break
            time.sleep(0.05)
        src.set_bumps(False)
        app.stop()
        report = app.train()
        accs = [r["acc"]["Full grid"] for r in report["models"] if r["acc"]["Full grid"] is not None]
        self.assertTrue(accs, "no model could cross-validate")
        self.assertGreaterEqual(max(accs), 0.6, f"CV accuracy too low (audio): {accs}")
        # live: 2 fresh knocks per zone, event-driven spacing
        last = max((e["id"] for e in app.events), default=0)
        expected = []
        for z in range(2):
            for _ in range(2):
                src.request_tap(z, 1, 2)
                expected.append(f"z{z}")
                t_end = time.monotonic() + 20
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
        live = list(zip(expected, evs))
        ok = sum(1 for want, ev in live if ev["pred"]["label"] == want)
        self.assertGreaterEqual(len(live), 3, f"too few live predictions: {len(live)}")
        self.assertGreaterEqual(ok / len(live), 0.75,
                                f"live accuracy too low (audio): {[(w, e['pred']) for w, e in live]}")
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
