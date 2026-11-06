"""App config / persistence tests (ported from the LidTap prototype, hardware-free)."""
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from wintap.app import App
from wintap.sources.synthetic import SyntheticSource


def make_app(tmp):
    return App(Path(tmp) / "data", source=SyntheticSource(realtime=False))


class AppConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = make_app(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rejects_non_finite_and_out_of_range_numbers(self):
        for body in ({"k": "nan"}, {"k": float("inf")}, {"k": 1e9}, {"refractory": -1}):
            with self.assertRaises(ValueError):
                self.app.set_config(body)

    def test_actions_keep_only_zone_keys(self):
        self.app.set_config({"actions": {"z0": "echo hi", "../x": "rm -rf /", "noise": "x"}})
        self.assertEqual(self.app.cfg["actions"], {"z0": "echo hi"})

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits (Windows uses ACLs)")
    def test_files_are_owner_only(self):
        self.app.set_config({"k": 7})
        mode = stat.S_IMODE(os.stat(self.app.dir / "config.json").st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.app.dir).st_mode), 0o700)

    def test_corrupt_files_are_moved_aside(self):
        (self.app.dir / "config.json").write_text("{broken")
        (self.app.dir / "dataset.json").write_text("[]")
        app = make_app(self.tmp.name)
        self.assertEqual(app.cfg["k"], 6.0)
        self.assertEqual(app.samples, [])
        self.assertTrue(list(self.app.dir.glob("config.json.corrupt-*")))

    def test_noise_recording_ends_without_a_gui(self):
        self.app.negatives_start({"seconds": 1})
        self.app.neg_until = time.time() - 1  # time is up, nobody polled status()
        ev = {"id": 1, "t": 0.0, "wall": time.time(), "g": np.zeros((160, 3)), "a": np.zeros((160, 3)),
              "peak_g": 0.0, "peak_a": 0.0, "lid": None, "threshold": 1.0, "noise": 0.1, "gated": None}
        self.app.on_event(ev)
        self.assertEqual(self.app.mode, "idle")
        self.assertEqual(self.app.samples, [])

    def test_dataset_roundtrip(self):
        self.app.set_config({"actions": {"z0": "lock"}})
        self.app.calibrate_start({"rows": 2, "cols": 2, "per_zone": 1, "block": 1})
        ev = {"id": 1, "t": 0.0, "wall": time.time(),
              "g": np.random.default_rng(0).normal(0, 5, (160, 3)),
              "a": np.random.default_rng(1).normal(0, 0.2, (160, 3)),
              "peak_g": 8.0, "peak_a": 0.2, "lid": None, "threshold": 1.0, "noise": 0.2, "gated": None}
        self.app.on_event(ev)
        self.assertEqual(len(self.app.samples), 1)
        self.assertTrue(self.app.samples[0]["label"].startswith("z"))
        # reload from disk: features are recomputed, config survives
        app2 = make_app(self.tmp.name)
        self.assertEqual(app2.cfg["actions"], {"z0": "lock"})
        self.assertEqual(len(app2.samples), 1)
        self.assertEqual(app2.samples[0]["f"].shape[0], 70)


if __name__ == "__main__":
    unittest.main()
