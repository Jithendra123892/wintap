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

Touch actions (lid as touchscreen): `tap` left-clicks at the tapped zone's center on
the screen, `click:fx,fy` / `move:fx,fy` target explicit screen fractions.
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
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

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


def screen_size():
    """Primary screen pixel size (SM_CXSCREEN=0, SM_CYSCREEN=1); sane fallback off-Windows."""
    if IS_WINDOWS:
        u = ctypes.windll.user32
        return u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return 1920, 1080


def _mouse_abs(x_px, y_px, flags):
    w, h = screen_size()
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(int(x_px / w * 65535), int(y_px / h * 65535), 0, flags, 0, 0)
    return inp


def tap_screen(fx, fy, sender=None, click=True):
    """Move the cursor to fraction (fx, fy) of the screen and optionally left-click.

    This is what turns the lid into a touchscreen: a lid zone maps to the same
    relative spot on the display, so knocking the lid 'touches' the screen there.
    """
    send = sender or _send_input
    w, h = screen_size()
    moves = [_mouse_abs(fx * w, fy * h, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)]
    if click:
        moves += [_mouse_abs(fx * w, fy * h, MOUSEEVENTF_LEFTDOWN),
                  _mouse_abs(fx * w, fy * h, MOUSEEVENTF_LEFTUP)]
    arr = (INPUT * len(moves))()
    for i, m in enumerate(moves):
        arr[i] = m
    return send(arr, len(moves))


def zone_center(zone, rows, cols):
    """Center of zone `zone` in a rows x cols lid grid, as screen fractions (fx, fy)."""
    r, c = divmod(zone, cols)
    return (c + 0.5) / cols, (r + 0.5) / rows


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


def run_action(spec, zone=None, sender=None, dry_run=False, grid=None, pos=None):
    """Run one configured action; returns a description string (or None for empty spec).

    spec may be a builtin name, "open:<program>", a shell command, or a touch action:
      tap            -> left-click at the tapped spot on the screen (lid = touchscreen);
                        uses `pos` (screen fractions) when given, else the zone center
      click:fx,fy    -> left-click at screen fraction (fx, fy)
      move:fx,fy     -> move cursor to screen fraction without clicking
    """
    spec = (spec or "").strip()
    if not spec:
        return None
    if zone is not None and "{zone}" in spec:
        spec = spec.replace("{zone}", str(zone + 1))
    if spec == "tap":
        if pos is not None:
            fx, fy = min(max(float(pos[0]), 0.0), 1.0), min(max(float(pos[1]), 0.0), 1.0)
        elif grid:
            fx, fy = zone_center(zone or 0, grid["rows"], grid["cols"])
        else:
            fx, fy = 0.5, 0.5
        if not dry_run:
            tap_screen(fx, fy, sender)
        return f"tap@({fx:.2f},{fy:.2f})"
    for prefix, click in (("click:", True), ("move:", False)):
        if spec.startswith(prefix):
            try:
                fx, fy = (float(v) for v in spec[len(prefix):].split(",")[:2])
            except ValueError:
                return None
            if not dry_run:
                tap_screen(min(max(fx, 0.0), 1.0), min(max(fy, 0.0), 1.0), sender, click=click)
            return f"{'click' if click else 'move'}@({fx:.2f},{fy:.2f})"
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
