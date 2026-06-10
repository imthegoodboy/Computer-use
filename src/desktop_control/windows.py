from __future__ import annotations

import ctypes
import time
from typing import Any, Mapping
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


def _text(value: object) -> str:
    return str(value or "").strip()


def _text_lc(value: object) -> str:
    return _text(value).casefold()


def _ref_int(ref: Mapping[str, Any], key: str) -> int | None:
    value = ref.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DesktopControlError(
            "invalid_window_ref",
            f"Window ref field {key} must be an integer",
            {"field": key, "value": value},
        ) from exc


def _ref_matches_identity(info: WindowInfo, ref: Mapping[str, Any]) -> bool:
    process_name = _text_lc(ref.get("process_name"))
    title = _text_lc(ref.get("title"))
    title_contains = _text_lc(ref.get("title_contains"))
    class_name = _text_lc(ref.get("class_name"))

    if process_name and _text_lc(info.process_name) != process_name:
        return False
    if title and _text_lc(info.title) != title:
        return False
    if title_contains and title_contains not in _text_lc(info.title):
        return False
    if class_name and not any((process_name, title, title_contains)) and _text_lc(info.class_name) != class_name:
        return False
    return True


def _exact_ref_matches_identity(info: WindowInfo, ref: Mapping[str, Any]) -> bool:
    if not _ref_matches_identity(info, ref):
        return False
    process_id = _ref_int(ref, "process_id")
    if process_id is not None and int(info.process_id) != process_id:
        return False
    return True


def _window_ref_score(info: WindowInfo, ref: Mapping[str, Any]) -> int:
    if not _ref_matches_identity(info, ref):
        return -1

    score = 0
    hwnd = _ref_int(ref, "hwnd")
    process_id = _ref_int(ref, "process_id")
    snapshot_id = _text(ref.get("snapshot_id"))
    if hwnd is not None and int(info.hwnd) == hwnd:
        score += 1000
    if _text_lc(ref.get("process_name")) and _text_lc(info.process_name) == _text_lc(ref.get("process_name")):
        score += 250
    if _text_lc(ref.get("title")) and _text_lc(info.title) == _text_lc(ref.get("title")):
        score += 300
    if _text_lc(ref.get("title_contains")) and _text_lc(ref.get("title_contains")) in _text_lc(info.title):
        score += 125
    if _text_lc(ref.get("class_name")) and _text_lc(info.class_name) == _text_lc(ref.get("class_name")):
        score += 175
    if process_id is not None and int(info.process_id) == process_id:
        score += 80
    if snapshot_id and info.snapshot_id() == snapshot_id:
        score += 60
    if info.visible:
        score += 10
    if not info.minimized:
        score += 5
    return score


def resolve_window_ref(
    ref: Mapping[str, Any],
    *,
    include_hidden: bool = False,
    allow_ambiguous: bool = False,
) -> WindowInfo:
    if not isinstance(ref, Mapping):
        raise DesktopControlError("invalid_window_ref", "Window ref must be an object")
    if not any(_text(ref.get(key)) for key in ("hwnd", "process_id", "process_name", "title", "title_contains", "class_name")):
        raise DesktopControlError(
            "invalid_window_ref",
            "Window ref must include at least one identity field",
            {"accepted_fields": ["hwnd", "process_id", "process_name", "title", "title_contains", "class_name"]},
        )

    hwnd = _ref_int(ref, "hwnd")
    if hwnd is not None:
        try:
            exact = get_window(hwnd)
        except DesktopControlError:
            exact = None
        if exact is not None and _exact_ref_matches_identity(exact, ref):
            return exact

    candidates: list[tuple[int, WindowInfo]] = []
    for window in list_windows(include_hidden=include_hidden):
        score = _window_ref_score(window, ref)
        if score >= 0:
            candidates.append((score, window))

    candidates.sort(key=lambda item: (item[0], item[1].visible, -item[1].hwnd), reverse=True)
    if not candidates:
        raise DesktopControlError(
            "window_recovery_failed",
            "Could not recover a matching window from the provided ref",
            {"window_ref": dict(ref)},
        )

    best_score, best = candidates[0]
    tied = [window for score, window in candidates[1:] if score == best_score]
    if tied and not allow_ambiguous:
        raise DesktopControlError(
            "window_recovery_ambiguous",
            "Multiple windows matched the provided ref with equal confidence",
            {
                "window_ref": dict(ref),
                "score": best_score,
                "matches": [best.to_dict(), *[window.to_dict() for window in tied[:4]]],
            },
        )

    return best


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
