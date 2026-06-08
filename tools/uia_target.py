from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import win32api
import win32con
import win32gui

EDIT_ID = 101
BUTTON_ID = 102


class UiaTarget:
    def __init__(self, title: str, log_path: Path, ready_path: Path) -> None:
        self.title = title
        self.log_path = log_path
        self.ready_path = ready_path
        self.class_name = f"DesktopControlUiaTarget_{int(time.time() * 1000)}"
        self.hwnd = 0
        self.edit_hwnd = 0
        self.button_hwnd = 0

    def log_event(self, event_type: str, **payload: object) -> None:
        data = {"type": event_type, "time": time.time(), **payload}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, separators=(",", ":")) + "\n")

    def wnd_proc(self, hwnd: int, message: int, wparam: int, lparam: int) -> int:
        if message == win32con.WM_COMMAND:
            control_id = int(wparam & 0xFFFF)
            notification = int((wparam >> 16) & 0xFFFF)
            text = win32gui.GetWindowText(self.edit_hwnd) if self.edit_hwnd else ""
            event_type = "button_invoked" if control_id == BUTTON_ID else "control_changed"
            self.log_event(
                event_type,
                control_id=control_id,
                notification=notification,
                text=text,
            )
            return 0

        if message == win32con.WM_PAINT:
            hdc, paint = win32gui.BeginPaint(hwnd)
            try:
                rect = win32gui.GetClientRect(hwnd)
                win32gui.FillRect(hdc, rect, win32gui.GetStockObject(win32con.WHITE_BRUSH))
                win32gui.TextOut(hdc, 40, 30, "UI Automation target")
                win32gui.TextOut(hdc, 40, 120, "Set the edit value and invoke Apply.")
            finally:
                win32gui.EndPaint(hwnd, paint)
            return 0

        if message == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    def create_controls(self) -> None:
        hinstance = win32api.GetModuleHandle(None)
        self.edit_hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_CLIENTEDGE,
            "Edit",
            "",
            win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.WS_TABSTOP | win32con.ES_AUTOHSCROLL,
            40,
            70,
            360,
            28,
            self.hwnd,
            EDIT_ID,
            hinstance,
            None,
        )
        self.button_hwnd = win32gui.CreateWindowEx(
            0,
            "Button",
            "Apply",
            win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.WS_TABSTOP | win32con.BS_PUSHBUTTON,
            420,
            68,
            90,
            32,
            self.hwnd,
            BUTTON_ID,
            hinstance,
            None,
        )

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
            260,
            180,
            580,
            280,
            0,
            0,
            hinstance,
            None,
        )
        self.create_controls()
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

    target = UiaTarget(args.title, Path(args.log), Path(args.ready))
    return target.run()


if __name__ == "__main__":
    raise SystemExit(main())
