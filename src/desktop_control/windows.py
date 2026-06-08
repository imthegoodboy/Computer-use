from __future__ import annotations

import ctypes
import time
from typing import Literal

import psutil
import win32con
import win32gui
import win32process

from .errors import DesktopControlError, wrap_os_error
from .models import Rect, WindowInfo

CoordinateSpace = Literal["window", "client", "screen"]
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.AttachThreadInput.argtypes = (ctypes.c_uint, ctypes.c_uint, ctypes.c_bool)
user32.AttachThreadInput.restype = ctypes.c_bool
user32.BringWindowToTop.argtypes = (ctypes.c_void_p,)
user32.BringWindowToTop.restype = ctypes.c_bool
user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.SetFocus.argtypes = (ctypes.c_void_p,)
user32.SetFocus.restype = ctypes.c_void_p
kernel32.GetCurrentThreadId.restype = ctypes.c_uint


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except (psutil.Error, OSError):
        return ""


def _window_info(hwnd: int) -> WindowInfo:
    if not win32gui.IsWindow(hwnd):
        raise DesktopControlError("window_not_found", f"Window handle {hwnd} is not valid")

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
        client_screen_left, client_screen_top = win32gui.ClientToScreen(hwnd, (client_left, client_top))
        client_screen_right, client_screen_bottom = win32gui.ClientToScreen(
            hwnd,
            (client_right, client_bottom),
        )
        return WindowInfo(
            hwnd=int(hwnd),
            title=win32gui.GetWindowText(hwnd) or "",
            process_id=int(pid),
            process_name=_process_name(int(pid)),
            class_name=win32gui.GetClassName(hwnd) or "",
            rect=Rect(int(left), int(top), int(right), int(bottom)),
            visible=bool(win32gui.IsWindowVisible(hwnd)),
            minimized=bool(win32gui.IsIconic(hwnd)),
            client_rect=Rect(
                int(client_screen_left),
                int(client_screen_top),
                int(client_screen_right),
                int(client_screen_bottom),
            ),
        )
    except Exception as exc:  # pywin32 raises several platform-specific exception types.
        raise wrap_os_error("window_query_failed", f"Could not query window {hwnd}", exc) from exc


def get_window(hwnd: int) -> WindowInfo:
    return _window_info(hwnd)


def list_windows(include_hidden: bool = False, query: str | None = None) -> list[WindowInfo]:
    query_lc = query.lower() if query else None
    windows: list[WindowInfo] = []

    def collect(hwnd: int, _: object) -> bool:
        try:
            info = _window_info(hwnd)
        except DesktopControlError:
            return True

        title_or_process = f"{info.title} {info.process_name}".lower()
        if not include_hidden and (not info.visible or not info.title.strip()):
            return True
        if info.rect.width <= 0 or info.rect.height <= 0:
            return True
        if query_lc and query_lc not in title_or_process:
            return True

        windows.append(info)
        return True

    win32gui.EnumWindows(collect, None)
    windows.sort(key=lambda w: (w.process_name.lower(), w.title.lower(), w.hwnd))
    return windows


def activate_window(hwnd: int, timeout_seconds: float = 2.0) -> WindowInfo:
    info = get_window(hwnd)
    errors: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if info.minimized:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            errors.append(repr(exc))

        if win32gui.GetForegroundWindow() == hwnd:
            return get_window(hwnd)

        _try_attached_foreground(hwnd, errors)
        if win32gui.GetForegroundWindow() == hwnd:
            return get_window(hwnd)

        time.sleep(0.03)

    raise DesktopControlError(
        "activation_timeout",
        f"Window {hwnd} did not become the foreground window",
        {"foreground_hwnd": int(win32gui.GetForegroundWindow()), "attempt_errors": errors[-5:]},
    )


def _try_attached_foreground(hwnd: int, errors: list[str]) -> None:
    current_thread = int(kernel32.GetCurrentThreadId())
    target_thread = int(win32process.GetWindowThreadProcessId(hwnd)[0])
    foreground_hwnd = int(win32gui.GetForegroundWindow())
    foreground_thread = (
        int(win32process.GetWindowThreadProcessId(foreground_hwnd)[0]) if foreground_hwnd else 0
    )
    attached: list[int] = []
    try:
        for thread_id in {target_thread, foreground_thread}:
            if thread_id and thread_id != current_thread:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    except Exception as exc:
        errors.append(repr(exc))
    finally:
        for thread_id in attached:
            user32.AttachThreadInput(current_thread, thread_id, False)


def resolve_point(hwnd: int, x: int, y: int, space: CoordinateSpace = "window") -> tuple[int, int]:
    if space == "screen":
        return int(x), int(y)
    if space == "client":
        sx, sy = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
        return int(sx), int(sy)
    if space == "window":
        info = get_window(hwnd)
        return int(info.rect.left + x), int(info.rect.top + y)
    raise DesktopControlError("invalid_coordinate_space", f"Unsupported coordinate space: {space}")


def require_point_in_window(hwnd: int, screen_x: int, screen_y: int) -> None:
    info = get_window(hwnd)
    if not info.rect.contains_screen_point(screen_x, screen_y):
        raise DesktopControlError(
            "point_out_of_bounds",
            "Target point is outside the window rectangle",
            {
                "hwnd": hwnd,
                "point": {"x": screen_x, "y": screen_y},
                "rect": info.rect.to_dict(),
            },
        )
