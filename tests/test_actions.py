"""Windows action tests: built-in key combos are built correctly (recorded, not sent),
{zone} substitution, dry-run never executes shell commands."""
import unittest

from wintap import actions


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, arr, count):
        self.calls.append([(arr[i].u.ki.wVk, arr[i].u.ki.dwFlags) for i in range(count)])
        return count


def vks(rec):
    return [vk for call in rec.calls for (vk, flags) in call if not flags]


class ActionTests(unittest.TestCase):
    def test_desktop_left_keys(self):
        rec = Recorder()
        actions.run_action("desktop_left", sender=rec)
        self.assertEqual(vks(rec), [actions.VK["LWIN"], actions.VK["LCONTROL"], actions.VK["LEFT"]])

    def test_play_pause_key(self):
        rec = Recorder()
        actions.run_action("play_pause", sender=rec)
        self.assertEqual(vks(rec), [actions.VK["MEDIA_PLAY_PAUSE"]])

    def test_lock_keys(self):
        rec = Recorder()
        actions.run_action("lock", sender=rec)
        self.assertEqual(vks(rec), [actions.VK["LWIN"], actions.VK["L"]])

    def test_keyup_pairs_present(self):
        rec = Recorder()
        actions.run_action("volume_up", sender=rec)
        ups = [vk for call in rec.calls for (vk, flags) in call if flags]
        self.assertEqual(ups, [actions.VK["VOLUME_UP"]])

    def test_builtin_dry_run_sends_nothing(self):
        rec = Recorder()
        actions.run_action("privacy_guard", sender=rec, dry_run=True)
        self.assertEqual(rec.calls, [])

    def test_zone_substitution_and_shell_dry_run(self):
        desc = actions.run_action("echo zone {zone}", zone=2, dry_run=True)
        self.assertEqual(desc, "echo zone 3")

    def test_open_prefix_dry_run(self):
        desc = actions.run_action("open:notepad.exe", dry_run=True)
        self.assertEqual(desc, "open:notepad.exe")

    def test_empty_spec(self):
        self.assertIsNone(actions.run_action("   "))

    def test_all_builtins_exist(self):
        for name in ("desktop_left", "desktop_right", "play_pause", "next_track", "prev_track",
                     "volume_up", "volume_down", "mute", "lock", "privacy_guard"):
            self.assertIn(name, actions.BUILTINS)


class MouseRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, arr, count):
        self.calls.append([(arr[i].type, arr[i].mi.dx, arr[i].mi.dy, arr[i].mi.dwFlags)
                           for i in range(count)])
        return count


class TouchActionTests(unittest.TestCase):
    def test_zone_center(self):
        self.assertEqual(actions.zone_center(0, 2, 2), (0.25, 0.25))
        self.assertEqual(actions.zone_center(3, 2, 2), (0.75, 0.75))
        self.assertEqual(actions.zone_center(1, 1, 2), (0.75, 0.5))

    def test_tap_sends_move_plus_click_at_zone_center(self):
        rec = MouseRecorder()
        desc = actions.run_action("tap", zone=1, grid={"rows": 1, "cols": 2}, sender=rec)
        self.assertEqual(desc, "tap@(0.75,0.50)")
        self.assertEqual(len(rec.calls), 1)
        evs = rec.calls[0]
        self.assertEqual(len(evs), 3)  # move, leftdown, leftup
        self.assertTrue(all(t == actions.INPUT_MOUSE for t, *_ in evs))
        self.assertEqual(evs[0][1], int(0.75 * 65535))  # 1920-wide fallback screen
        self.assertTrue(evs[0][3] & actions.MOUSEEVENTF_ABSOLUTE)
        self.assertTrue(evs[1][3] & actions.MOUSEEVENTF_LEFTDOWN)
        self.assertTrue(evs[2][3] & actions.MOUSEEVENTF_LEFTUP)

    def test_click_and_move_explicit_fractions(self):
        rec = MouseRecorder()
        self.assertEqual(actions.run_action("click:0.1,0.9", sender=rec), "click@(0.10,0.90)")
        self.assertEqual(len(rec.calls[0]), 3)
        rec2 = MouseRecorder()
        self.assertEqual(actions.run_action("move:0.5,0.5", sender=rec2), "move@(0.50,0.50)")
        self.assertEqual(len(rec2.calls[0]), 1)  # move only, no click

    def test_fractions_are_clamped(self):
        rec = MouseRecorder()
        actions.run_action("click:2.0,-1.0", sender=rec)
        evs = rec.calls[0]
        self.assertEqual(evs[0][1], 65535)
        self.assertEqual(evs[0][2], 0)

    def test_tap_dry_run_sends_nothing(self):
        rec = MouseRecorder()
        desc = actions.run_action("tap", zone=0, grid={"rows": 2, "cols": 2}, sender=rec, dry_run=True)
        self.assertEqual(desc, "tap@(0.25,0.25)")
        self.assertEqual(rec.calls, [])

    def test_bad_fraction_is_noop(self):
        rec = MouseRecorder()
        self.assertIsNone(actions.run_action("click:abc", sender=rec))
        self.assertEqual(rec.calls, [])


if __name__ == "__main__":
    unittest.main()
