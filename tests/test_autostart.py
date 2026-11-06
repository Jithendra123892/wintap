import argparse
import os
import tempfile
import unittest
from pathlib import Path

from wintap.__main__ import cmd_autostart


def _args(action, port=8765):
    return argparse.Namespace(action=action, port=port)


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._old
        self._tmp.cleanup()

    def _bat(self):
        return Path(self._tmp.name) / r"Microsoft\Windows\Start Menu\Programs\Startup" / "wintap.bat"

    def test_on_creates_startup_entry_off_removes_it(self):
        cmd_autostart(_args("status"))
        self.assertFalse(self._bat().exists())
        cmd_autostart(_args("on", port=8899))
        self.assertTrue(self._bat().exists())
        text = self._bat().read_text()
        self.assertIn("-m wintap serve --port 8899", text)
        cmd_autostart(_args("off"))
        self.assertFalse(self._bat().exists())
        cmd_autostart(_args("off"))  # idempotent

    def test_status_reports_state(self):
        cmd_autostart(_args("status"))  # OFF path prints, must not raise
        cmd_autostart(_args("on"))
        cmd_autostart(_args("status"))  # ON path


if __name__ == "__main__":
    unittest.main()
