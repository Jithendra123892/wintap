"""Windows zone actions.

Config maps a zone label (z0..zN) to an action string. An action is one of:

  desktop_left / desktop_right   Win+Ctrl+Left / Right (virtual desktops)
  play_pause / next_track / prev_track   media keys
  volume_up / volume_down / mute         volume keys
  lock                               Win+L
  privacy_guard                      Win+L (lock session) + mute every capture endpoint
                                     (CoreAudio) + deny camera access (registry consent)
  open:<program>                     launch via cmd /c start
  anything else                      run as a shell command ({zone} -> zone number)

Keys are sent with SendInput. `sender` and `dry_run` exist for tests and --dry-run.
"""
import ctypes
import subprocess
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

VK = {
    "LWIN": 0x5B, "LCONTROL": 0xA2, "LEFT": 0x25, "RIGHT": 0x27, "L": 0x4C,
    "MEDIA_NEXT_TRACK": 0xB0, "MEDIA_PREV_TRACK": 0xB1, "MEDIA_PLAY_PAUSE": 0xB3,
    "VOLUME_MUTE": 0xAD, "VOLUME_DOWN": 0xAE, "VOLUME_UP": 0xAF,
}

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

# ctypes structures are platform-neutral; only the SendInput call itself needs Windows.
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _send_input(arr, count):
    if IS_WINDOWS:
        return ctypes.windll.user32.SendInput(count, arr, ctypes.sizeof(INPUT))
    return 0


def _key(vk, up=False):
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return inp


def send_keys(vks, sender=None):
    """Press and release a key combination (list of VK codes)."""
    send = sender or _send_input
    n = len(vks)
    arr = (INPUT * (2 * n))()
    for i, vk in enumerate(vks):
        arr[i] = _key(vk)
        arr[2 * n - 1 - i] = _key(vk, up=True)
    return send(arr, 2 * n)


def _mute_all_mics():
    """Mute every active capture endpoint via CoreAudio (needs pip install wintap[privacy])."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        eCapture, DEVICE_STATE_ACTIVE = 1, 1
        coll = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE)
        for i in range(coll.GetCount()):
            dev = coll.Item(i)
            iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            cast(iface, POINTER(IAudioEndpointVolume)).SetMute(1, None)
    except Exception:
        pass


def _camera_off():
    """Deny camera access: per-user consent (HKCU) and machine-wide (HKLM, needs admin)."""
    if not IS_WINDOWS:
        return
    import winreg
    path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Value", 0, winreg.REG_SZ, "Deny")
            winreg.CloseKey(key)
        except Exception:
            pass


def privacy_guard(sender=None):
    send_keys([VK["LWIN"], VK["L"]], sender)  # lock the session: instant and always works
    _mute_all_mics()
    _camera_off()


BUILTINS = {
    "desktop_left": lambda s: send_keys([VK["LWIN"], VK["LCONTROL"], VK["LEFT"]], s),
    "desktop_right": lambda s: send_keys([VK["LWIN"], VK["LCONTROL"], VK["RIGHT"]], s),
    "play_pause": lambda s: send_keys([VK["MEDIA_PLAY_PAUSE"]], s),
    "next_track": lambda s: send_keys([VK["MEDIA_NEXT_TRACK"]], s),
    "prev_track": lambda s: send_keys([VK["MEDIA_PREV_TRACK"]], s),
    "volume_up": lambda s: send_keys([VK["VOLUME_UP"]], s),
    "volume_down": lambda s: send_keys([VK["VOLUME_DOWN"]], s),
    "mute": lambda s: send_keys([VK["VOLUME_MUTE"]], s),
    "lock": lambda s: send_keys([VK["LWIN"], VK["L"]], s),
    "privacy_guard": privacy_guard,
}

_DEVNULL = subprocess.DEVNULL


def run_action(spec, zone=None, sender=None, dry_run=False):
    """Run one configured action; returns a description string (or None for empty spec)."""
    spec = (spec or "").strip()
    if not spec:
        return None
    if zone is not None and "{zone}" in spec:
        spec = spec.replace("{zone}", str(zone + 1))
    if spec in BUILTINS:
        if not dry_run:
            BUILTINS[spec](sender)
        return f"builtin:{spec}"
    name, _, arg = spec.partition(":")
    if name == "open" and arg:
        if not dry_run:
            subprocess.Popen(["cmd", "/c", "start", "", arg], stdout=_DEVNULL, stderr=_DEVNULL)
        return f"open:{arg}"
    if not dry_run:
        subprocess.Popen(spec, shell=True, stdout=_DEVNULL, stderr=_DEVNULL)
    return spec
