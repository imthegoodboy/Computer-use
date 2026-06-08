from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import win32api
import win32con
import win32gui

WM_MESSAGES = {
    win32con.WM_MOUSEMOVE: "motion",
    win32con.WM_LBUTTONDOWN: "button_press",
    win32con.WM_LBUTTONUP: "button_release",
    win32con.WM_RBUTTONDOWN: "right_button_press",
    win32con.WM_RBUTTONUP: "right_button_release",
    win32con.WM_MBUTTONDOWN: "middle_button_press",
    win32con.WM_MBUTTONUP: "middle_button_release",
    win32con.WM_MOUSEWHEEL: "mouse_wheel",
}


def signed_word(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def point_from_lparam(lparam: int) -> tuple[int, int]:
    return signed_word(lparam), signed_word(lparam >> 16)


def wheel_delta_from_wparam(wparam: int) -> int:
    return signed_word(wparam >> 16)


class MouseTarget:
    def __init__(self, title: str, log_path: Path, ready_path: Path) -> None:
        self.title = title
        self.log_path = log_path
        self.ready_path = ready_path
        self.class_name = f"DesktopControlMouseTarget_{int(time.time() * 1000)}"
        self.hwnd = 0
        self.left_button_down = False

    def log_event(self, event_type: str, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        client_x, client_y = point_from_lparam(lparam)
        if message == win32con.WM_MOUSEWHEEL:
            screen_x, screen_y = point_from_lparam(lparam)
            client_x, client_y = win32gui.ScreenToClient(hwnd, (screen_x, screen_y))
            delta = wheel_delta_from_wparam(wparam)
        else:
            screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
            delta = 0

        payload = {
            "type": event_type,
            "message": int(message),
            "time": time.time(),
            "x": int(client_x),
            "y": int(client_y),
            "x_root": int(screen_x),
            "y_root": int(screen_y),
            "button": 1 if event_type in {"button_press", "button_release", "drag_motion"} else 0,
            "delta": int(delta),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")

    def wnd_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message in WM_MESSAGES:
            event_type = WM_MESSAGES[message]
            if message == win32con.WM_LBUTTONDOWN:
                self.left_button_down = True
            elif message == win32con.WM_LBUTTONUP:
                self.left_button_down = False
            elif message == win32con.WM_MOUSEMOVE and self.left_button_down:
                event_type = "drag_motion"
            self.log_event(event_type, hwnd, message, wparam, lparam)
            return 0
        if message == win32con.WM_PAINT:
            hdc, paint = win32gui.BeginPaint(hwnd)
            try:
                rect = win32gui.GetClientRect(hwnd)
                win32gui.FillRect(hdc, rect, win32gui.GetStockObject(win32con.WHITE_BRUSH))
                win32gui.Rectangle(hdc, 80, 80, 480, 320)
                win32gui.TextOut(hdc, 24, 24, "Mouse target")
                win32gui.TextOut(hdc, 100, 100, "Click, drag, move, and scroll here.")
            finally:
                win32gui.EndPaint(hwnd, paint)
            return 0
        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def run(self) -> int:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.ready_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")

        hinstance = win32api.GetModuleHandle(None)
        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = hinstance
        wndclass.lpszClassName = self.class_name
        wndclass.lpfnWndProc = self.wnd_proc
        wndclass.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
        wndclass.hbrBackground = win32gui.GetStockObject(win32con.WHITE_BRUSH)
        win32gui.RegisterClass(wndclass)

        self.hwnd = win32gui.CreateWindowEx(
            0,
            self.class_name,
            self.title,
            win32con.WS_OVERLAPPEDWINDOW,
            220,
            160,
            560,
            420,
            0,
            0,
            hinstance,
            None,
        )
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
        win32gui.UpdateWindow(self.hwnd)
        win32gui.SetForegroundWindow(self.hwnd)
        self.ready_path.write_text("ready", encoding="utf-8")
        win32gui.PumpMessages()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--ready", required=True)
    args = parser.parse_args()

    target = MouseTarget(args.title, Path(args.log), Path(args.ready))
    return target.run()


if __name__ == "__main__":
    raise SystemExit(main())
