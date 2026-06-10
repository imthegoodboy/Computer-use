import pytest

from desktop_control import apps as apps_module
from desktop_control.apps import AppInfo, launch_app, list_apps
from desktop_control.errors import DesktopControlError
from desktop_control.models import Rect, WindowInfo


def window(hwnd=100, process_id=10, process_name="notepad.exe"):
    return WindowInfo(
        hwnd=hwnd,
        title="Untitled - Notepad",
        process_id=process_id,
        process_name=process_name,
        class_name="Notepad",
        rect=Rect(0, 0, 500, 400),
        visible=True,
        minimized=False,
        client_rect=Rect(8, 32, 492, 392),
    )


def app(
    id="app",
    display_name="Notepad",
    source="start_menu",
    launch_path="C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Notepad.lnk",
    executable_path="C:\\Windows\\System32\\notepad.exe",
    process_name="notepad.exe",
    running=False,
    process_ids=None,
    windows=None,
):
    return AppInfo(
        id=id,
        display_name=display_name,
        source=source,
        launch_path=launch_path,
        executable_path=executable_path,
        process_name=process_name,
        running=running,
        process_ids=process_ids or [],
        windows=windows or [],
    )


def test_list_apps_merges_start_menu_and_running_process(monkeypatch):
    running_window = window()
    monkeypatch.setattr(apps_module, "_start_menu_apps", lambda: [app(id="shortcut")])
    monkeypatch.setattr(
        apps_module,
        "_running_apps",
        lambda include_windows=True: [
            app(id="running", source="running", running=True, process_ids=[10], windows=[running_window])
        ],
    )

    result = list_apps(query="note")

    assert len(result) == 1
    assert result[0].running is True
    assert result[0].process_ids == [10]
    assert result[0].windows == [running_window]
    assert result[0].source == "running+start_menu"


def test_list_apps_filters_by_query(monkeypatch):
    monkeypatch.setattr(
        apps_module,
        "_start_menu_apps",
        lambda: [
            app(
                display_name="Calculator",
                process_name="calc.exe",
                launch_path="C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Calculator.lnk",
                executable_path="C:\\Windows\\System32\\calc.exe",
            )
        ],
    )
    monkeypatch.setattr(apps_module, "_running_apps", lambda include_windows=True: [])

    assert list_apps(query="notepad") == []
    assert list_apps(query="calc")[0].display_name == "Calculator"


def test_launch_app_uses_shell_execute_and_waits(monkeypatch):
    captured = {}
    monkeypatch.setattr(apps_module, "find_app", lambda selector: app())

    def fake_shell_execute(file, args=None, cwd=None):
        captured["file"] = file
        captured["args"] = args
        captured["cwd"] = cwd
        return 33

    monkeypatch.setattr(apps_module, "_shell_execute", fake_shell_execute)
    monkeypatch.setattr(
        apps_module,
        "wait_for_window",
        lambda query, timeout_seconds=10.0, interval_seconds=0.1: {
            "ok": True,
            "attempts": 2,
            "window": {"hwnd": 123, "title": "Untitled - Notepad"},
        },
    )

    result = launch_app("Notepad", args=["file.txt"], cwd="C:\\Temp", wait_query="Notepad")

    assert result["ok"] is True
    assert result["window"]["hwnd"] == 123
    assert captured == {
        "file": "C:\\Windows\\System32\\notepad.exe",
        "args": ["file.txt"],
        "cwd": "C:\\Temp",
    }


def test_launch_app_blocks_terminal_process(monkeypatch):
    monkeypatch.setattr(apps_module, "find_app", lambda selector: None)
    monkeypatch.setattr(apps_module, "_shell_execute", lambda *args, **kwargs: 33)

    with pytest.raises(DesktopControlError) as exc_info:
        launch_app("pwsh", wait=False)

    assert exc_info.value.code == "policy_denied"
