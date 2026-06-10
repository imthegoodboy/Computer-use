import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.models import Rect, WindowInfo
from desktop_control import windows as windows_module


def make_window(
    hwnd=100,
    title="Target",
    process_id=10,
    process_name="target.exe",
    class_name="TargetWindow",
):
    return WindowInfo(
        hwnd=hwnd,
        title=title,
        process_id=process_id,
        process_name=process_name,
        class_name=class_name,
        rect=Rect(0, 0, 500, 400),
        visible=True,
        minimized=False,
        client_rect=Rect(8, 32, 492, 392),
    )


def test_window_dict_contains_recoverable_window_ref():
    window = make_window()
    payload = window.to_dict()

    assert payload["window_ref"] == window.window_ref()
    assert payload["window_ref"]["hwnd"] == 100
    assert payload["window_ref"]["process_name"] == "target.exe"
    assert payload["window_ref"]["snapshot_id"] == payload["snapshot_id"]


def test_resolve_window_ref_uses_valid_matching_hwnd(monkeypatch):
    window = make_window(hwnd=123)
    monkeypatch.setattr(windows_module, "get_window", lambda hwnd: window)

    result = windows_module.resolve_window_ref(window.window_ref())

    assert result is window


def test_resolve_window_ref_rejects_reused_hwnd_with_different_process_id(monkeypatch):
    stale = make_window(hwnd=123, process_id=10)
    reused = make_window(hwnd=123, process_id=99)
    recovered = make_window(hwnd=456, process_id=20)

    monkeypatch.setattr(windows_module, "get_window", lambda hwnd: reused)
    monkeypatch.setattr(windows_module, "list_windows", lambda include_hidden=False: [recovered])

    result = windows_module.resolve_window_ref(stale.window_ref())

    assert result.hwnd == 456


def test_resolve_window_ref_falls_back_when_hwnd_is_stale(monkeypatch):
    stale = make_window(hwnd=111, process_id=10)
    recovered = make_window(hwnd=222, process_id=20)

    def fake_get_window(hwnd):
        raise DesktopControlError("window_not_found", "missing")

    monkeypatch.setattr(windows_module, "get_window", fake_get_window)
    monkeypatch.setattr(windows_module, "list_windows", lambda include_hidden=False: [recovered])

    result = windows_module.resolve_window_ref(stale.window_ref())

    assert result.hwnd == 222


def test_resolve_window_ref_allows_class_name_change_with_strong_identity(monkeypatch):
    stale = make_window(hwnd=111, class_name="DynamicClassA")
    recovered = make_window(hwnd=222, process_id=20, class_name="DynamicClassB")

    def fake_get_window(hwnd):
        raise DesktopControlError("window_not_found", "missing")

    monkeypatch.setattr(windows_module, "get_window", fake_get_window)
    monkeypatch.setattr(windows_module, "list_windows", lambda include_hidden=False: [recovered])

    result = windows_module.resolve_window_ref(stale.window_ref())

    assert result.hwnd == 222


def test_resolve_window_ref_rejects_ambiguous_matches(monkeypatch):
    first = make_window(hwnd=201, process_id=21)
    second = make_window(hwnd=202, process_id=22)

    def fake_get_window(hwnd):
        raise DesktopControlError("window_not_found", "missing")

    monkeypatch.setattr(windows_module, "get_window", fake_get_window)
    monkeypatch.setattr(windows_module, "list_windows", lambda include_hidden=False: [first, second])

    with pytest.raises(DesktopControlError) as exc_info:
        windows_module.resolve_window_ref({"process_name": "target.exe", "title": "Target", "class_name": "TargetWindow"})

    assert exc_info.value.code == "window_recovery_ambiguous"


def test_resolve_window_ref_fails_without_identity():
    with pytest.raises(DesktopControlError) as exc_info:
        windows_module.resolve_window_ref({})

    assert exc_info.value.code == "invalid_window_ref"
