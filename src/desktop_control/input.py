from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

import win32clipboard
import win32con

from .errors import DesktopControlError

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
user32 = ctypes.WinDLL("user32", use_last_error=True)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]

    @property
    def mi(self) -> MOUSEINPUT:
        return self.union.mi

    @mi.setter
    def mi(self, value: MOUSEINPUT) -> None:
        self.union.mi = value

    @property
    def ki(self) -> KEYBDINPUT:
        return self.union.ki

    @ki.setter
    def ki(self, value: KEYBDINPUT) -> None:
        self.union.ki = value


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = wintypes.BOOL


VK_CODES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "meta": 0x5B,
}
VK_CODES.update({f"f{i}": 0x6F + i for i in range(1, 25)})


def _raise_last_error(code: str, message: str) -> None:
    error = ctypes.get_last_error()
    raise DesktopControlError(code, message, {"win32_error": error})


def _mouse_input(flags: int, data: int = 0) -> INPUT:
    item = INPUT()
    item.type = INPUT_MOUSE
    item.mi = MOUSEINPUT(0, 0, int(data), int(flags), 0, 0)
    return item


def _key_input(vk: int, scan: int, flags: int) -> INPUT:
    item = INPUT()
    item.type = INPUT_KEYBOARD
    item.ki = KEYBDINPUT(int(vk), int(scan), int(flags), 0, 0)
    return item


def _send_inputs(inputs: list[INPUT]) -> None:
    if not inputs:
        return
    array_type = INPUT * len(inputs)
    array = array_type(*inputs)
    sent = user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        _raise_last_error("send_input_failed", "SendInput did not accept every input event")


def set_cursor_pos(x: int, y: int) -> None:
    if not user32.SetCursorPos(int(x), int(y)):
        _raise_last_error("cursor_move_failed", "Could not move the cursor")


def move_to(x: int, y: int) -> None:
    set_cursor_pos(x, y)


def click_at(x: int, y: int, button: str = "left", count: int = 1, interval_seconds: float = 0.05) -> None:
    down_up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button)
    if not down_up:
        raise DesktopControlError("invalid_button", f"Unsupported mouse button: {button}")

    set_cursor_pos(x, y)
    for index in range(max(1, int(count))):
        _send_inputs([_mouse_input(down_up[0]), _mouse_input(down_up[1])])
        if index + 1 < count:
            time.sleep(interval_seconds)


def scroll_at(x: int, y: int, delta: int) -> None:
    set_cursor_pos(x, y)
    _send_inputs([_mouse_input(MOUSEEVENTF_WHEEL, int(delta) * WHEEL_DELTA)])


def drag_at(
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    button: str = "left",
    duration_seconds: float = 0.2,
    steps: int = 12,
) -> None:
    down_up = {
        "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
        "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
        "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
    }.get(button)
    if not down_up:
        raise DesktopControlError("invalid_button", f"Unsupported mouse button: {button}")

    set_cursor_pos(from_x, from_y)
    _send_inputs([_mouse_input(down_up[0])])
    total_steps = max(1, int(steps))
    sleep_time = max(0.0, float(duration_seconds)) / total_steps
    for step in range(1, total_steps + 1):
        ratio = step / total_steps
        x = round(from_x + (to_x - from_x) * ratio)
        y = round(from_y + (to_y - from_y) * ratio)
        set_cursor_pos(x, y)
        if sleep_time:
            time.sleep(sleep_time)
    _send_inputs([_mouse_input(down_up[1])])


def _vk_for_key(key: str) -> int:
    normalized = key.strip().lower()
    if len(normalized) == 1:
        char = normalized.upper()
        if "A" <= char <= "Z" or "0" <= char <= "9":
            return ord(char)
    if normalized in VK_CODES:
        return VK_CODES[normalized]
    raise DesktopControlError("invalid_key", f"Unsupported key: {key}")


def parse_chord(chord: str) -> list[str]:
    keys = [part.strip() for part in chord.split("+") if part.strip()]
    if not keys:
        raise DesktopControlError("invalid_key_chord", "Key chord cannot be empty")
    return keys


def press_chord(chord: str) -> None:
    keys = parse_chord(chord)
    vks = [_vk_for_key(key) for key in keys]
    inputs = [_key_input(vk, 0, 0) for vk in vks]
    inputs.extend(_key_input(vk, 0, KEYEVENTF_KEYUP) for vk in reversed(vks))
    _send_inputs(inputs)


def press_key_sequence(chords: list[str], interval_seconds: float = 0.03) -> None:
    for index, chord in enumerate(chords):
        press_chord(chord)
        if index + 1 < len(chords):
            time.sleep(interval_seconds)


def type_text_unicode(text: str) -> None:
    inputs: list[INPUT] = []
    for char in text:
        if char in {"\r", "\n"}:
            vk = VK_CODES["enter"]
            inputs.append(_key_input(vk, 0, 0))
            inputs.append(_key_input(vk, 0, KEYEVENTF_KEYUP))
            continue
        if char == "\t":
            vk = VK_CODES["tab"]
            inputs.append(_key_input(vk, 0, 0))
            inputs.append(_key_input(vk, 0, KEYEVENTF_KEYUP))
            continue
        codepoint = ord(char)
        if codepoint > 0xFFFF:
            raise DesktopControlError("unsupported_text", "Only BMP Unicode characters are supported")
        inputs.append(_key_input(0, codepoint, KEYEVENTF_UNICODE))
        inputs.append(_key_input(0, codepoint, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    _send_inputs(inputs)


def paste_text(text: str, restore_clipboard: bool = True) -> None:
    previous_text: str | None = None
    had_previous_text = False

    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            try:
                previous_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                had_previous_text = True
            except Exception:
                previous_text = None
                had_previous_text = False
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()

    try:
        press_chord("ctrl+v")
        time.sleep(0.12)
    finally:
        if restore_clipboard:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                if had_previous_text and previous_text is not None:
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, previous_text)
            finally:
                win32clipboard.CloseClipboard()


def send_text(text: str, method: str = "clipboard") -> None:
    if method == "clipboard":
        paste_text(text)
        return
    if method == "unicode":
        type_text_unicode(text)
        return
    raise DesktopControlError("invalid_text_method", f"Unsupported text entry method: {method}")
