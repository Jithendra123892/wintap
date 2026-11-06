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


if __name__ == "__main__":
    unittest.main()
