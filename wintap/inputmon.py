"""Windows input gating and lid state (drop-in for the macOS calls in the LidTap prototype).

- Typing / click / scroll timestamps come from WH_KEYBOARD_LL / WH_MOUSE_LL low-level hooks.
  These are global, in-process (hMod = NULL), need no admin and no accessibility permission.
- Lid open/closed comes from a message-only window + RegisterPowerSettingNotification with
  GUID_LIDSWITCH_STATE_CHANGE (BA3E0F4D-B817-4094-A2D1-D56379E6A0F3), delivered as
  WM_POWERBROADCAST / PBT_POWERSETTINGCHANGE.

Everything runs on one daemon thread with a Win32 message loop. Any failure (headless
session, non-Windows) degrades to "no recent input" and "lid unknown" instead of crashing.
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_MOUSEWHEEL = 0x020A
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_POWERBROADCAST = 0x0218
PBT_POWERSETTINGCHANGE = 0x8013
HWND_MESSAGE = -3
DEVICE_NOTIFY_WINDOW_HANDLE = 0


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


LID_GUID = _GUID(0xBA3E0F4D, 0xB817, 0x4094,
                 (ctypes.c_ubyte * 8)(0xA2, 0xD1, 0xD5, 0x63, 0x79, 0xE6, 0xA0, 0xF3))


class _State:
    def __init__(self):
        self.lock = threading.Lock()
        self.last = {"typing": None, "click": None, "scroll": None}
        self.lid_open = None


_state = _State()
_started = False


def seconds_since_input():
    """Seconds since the last keyboard / click / scroll event, on the monotonic clock."""
    now = time.monotonic()
    with _state.lock:
        return {k: (1e9 if v is None else now - v) for k, v in _state.last.items()}


class LidState:
    @property
    def angle(self):
        """Lid as degrees for the detector's gate: 130 open, 0 closed, None unknown."""
        with _state.lock:
            o = _state.lid_open
        return None if o is None else (130.0 if o else 0.0)


def lid_state():
    return LidState()


if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _LRESULT = ctypes.c_ssize_t  # wintypes.LRESULT only exists on 3.12+
    _WPARAM = ctypes.c_size_t
    _LPARAM = ctypes.c_ssize_t
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
    _user32.CallNextHookEx.restype = _LRESULT
    _user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
    _user32.RegisterPowerSettingNotification.argtypes = [wintypes.HWND, ctypes.POINTER(_GUID), wintypes.DWORD]
    _user32.DefWindowProcW.restype = _LRESULT
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, _WPARAM, _LPARAM]
    _user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

    HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, _WPARAM, _LPARAM)
    WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, wintypes.UINT, _WPARAM, _LPARAM)

    def _kbd_cb(nCode, wParam, lParam):
        if nCode == HC_ACTION and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            with _state.lock:
                _state.last["typing"] = time.monotonic()
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _mouse_cb(nCode, wParam, lParam):
        if nCode == HC_ACTION:
            if wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                with _state.lock:
                    _state.last["click"] = time.monotonic()
            elif wParam == WM_MOUSEWHEEL:
                with _state.lock:
                    _state.last["scroll"] = time.monotonic()
        return _user32.CallNextHookEx(None, nCode, wParam, lParam)

    _KBD_CB = HOOKPROC(_kbd_cb)    # keep refs alive for the lifetime of the process
    _MOUSE_CB = HOOKPROC(_mouse_cb)

    class _POWERBROADCAST_SETTING(ctypes.Structure):
        _fields_ = [("PowerSetting", _GUID), ("DataLength", wintypes.DWORD), ("Data", ctypes.c_ubyte * 4)]

    _guid_bytes = ctypes.string_at(ctypes.byref(LID_GUID), 16)

    def _wnd_proc(hwnd, msg, wParam, lParam):
        if msg == WM_POWERBROADCAST and wParam == PBT_POWERSETTINGCHANGE and lParam:
            try:
                ps = _POWERBROADCAST_SETTING.from_address(lParam)
                if ctypes.string_at(ctypes.byref(ps.PowerSetting), 16) == _guid_bytes and ps.DataLength >= 4:
                    is_open = int.from_bytes(bytes(ps.Data[:4]), "little") != 0
                    with _state.lock:
                        _state.lid_open = is_open
            except Exception:
                pass
        return _user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    _WNDPROC = WNDPROC(_wnd_proc)

    def _thread_main():
        try:
            _user32.SetWindowsHookExW(WH_KEYBOARD_LL, _KBD_CB, None, 0)
            _user32.SetWindowsHookExW(WH_MOUSE_LL, _MOUSE_CB, None, 0)
            hwnd = _user32.CreateWindowExW(0, "Message", None, 0, 0, 0, 0, 0,
                                           wintypes.HWND(HWND_MESSAGE), None, None, None)
            if hwnd:
                _user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(LID_GUID),
                                                         DEVICE_NOTIFY_WINDOW_HANDLE)
            msg = wintypes.MSG()
            while True:
                r = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass  # headless session: gating degrades to "no recent input"
else:
    def _thread_main():
        pass


def start():
    global _started
    if _started:
        return
    _started = True
    if IS_WINDOWS:
        threading.Thread(target=_thread_main, daemon=True, name="wintap-inputmon").start()
