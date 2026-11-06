"""Auto source selection: the mic is a FALLBACK, used only when the machine exposes
no IMU to Windows (neither a WinRT sensor class device nor a HID motion sensor)."""
import unittest
from unittest import mock

import wintap.sources as S


class AutoSourceTests(unittest.TestCase):
    def _auto(self, winrt, hid, audio):
        with mock.patch.object(S, "winrt_sensor_present", return_value=winrt), \
             mock.patch.object(S, "hid_sensor_present", return_value=hid), \
             mock.patch.object(S, "audio_input_present", return_value=audio):
            return S.make_source("auto").kind

    def test_winrt_wins_over_hid_and_mic(self):
        self.assertEqual(self._auto(True, True, True), "winrt")

    def test_hid_wins_over_mic(self):
        self.assertEqual(self._auto(False, True, True), "hid")

    def test_mic_only_when_no_imu(self):
        self.assertEqual(self._auto(False, False, True), "audio")

    def test_no_sensor_no_mic_still_starts_and_reports_error(self):
        # must not crash: the winrt source starts and surfaces a clear "no IMU" error
        self.assertEqual(self._auto(False, False, False), "winrt")

    def test_explicit_audio_still_selectable(self):
        src = S.make_source("audio", live=False)
        self.assertEqual(src.kind, "audio")


if __name__ == "__main__":
    unittest.main()
