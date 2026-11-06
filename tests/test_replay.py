"""Record a synthetic session to JSONL (the `monitor --record` format), then replay it
into a fresh App and require the detector to fire on the recorded taps."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from wintap.app import App
from wintap.sources import make_source
from wintap.sources.synthetic import SyntheticSource


class ReplayTests(unittest.TestCase):
    def test_record_then_replay_detects_taps(self):
        tmp = tempfile.TemporaryDirectory()
        rec = Path(tmp.name) / "rec.jsonl"
        src = SyntheticSource(fs=800, realtime=False, seed=11)
        app = App(Path(tmp.name) / "d1", source=src)
        app.start()
        with rec.open("w", encoding="utf-8") as f:
            app.sensors.on_sample = lambda k, t, x, y, z: f.write(
                json.dumps({"k": k, "t": t, "x": x, "y": y, "z": z}) + "\n")
            src.request_tap(0, 2, 2)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not app.events:
                time.sleep(0.02)
            src.request_tap(3, 2, 2)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and len(app.events) < 2:
                time.sleep(0.02)
            app.sensors.on_sample = None
        self.assertGreaterEqual(len(app.events), 2, "source session produced no tap events")
        with rec.open(encoding="utf-8") as rf:
            n_rows = sum(1 for _ in rf)
        self.assertGreater(n_rows, 500, f"recording too small: {n_rows} rows")

        rsrc = make_source(f"replay:{rec}", realtime=False)
        self.assertEqual(rsrc.kind, "replay")
        app2 = App(Path(tmp.name) / "d2", source=rsrc)
        app2.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and len(app2.events) < 2:
            time.sleep(0.02)
        self.assertGreaterEqual(len(app2.events), 2,
                                "replay produced no tap events")
        peaks = [round(e["peak_g"], 1) for e in app2.events]
        self.assertTrue(all(p > 2.0 for p in peaks), f"replayed peaks too weak: {peaks}")

    def test_replay_missing_file_reports_error(self):
        rsrc = make_source("replay:C:/no/such/file.jsonl", realtime=False)
        rsrc.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not rsrc.error:
            time.sleep(0.02)
        self.assertTrue(rsrc.error)


if __name__ == "__main__":
    unittest.main()
