import pytest

from desktop_control.errors import DesktopControlError
from desktop_control import wait as wait_module


def test_wait_for_window_returns_first_match(monkeypatch):
    class Window:
        def to_dict(self):
            return {"hwnd": 1}

    monkeypatch.setattr(wait_module, "list_windows", lambda include_hidden=False, query=None: [Window()])
    result = wait_module.wait_for_window(query="target", timeout_seconds=0.01, interval_seconds=0.01)
    assert result["ok"] is True
    assert result["window"]["hwnd"] == 1


def test_wait_for_window_times_out(monkeypatch):
    monkeypatch.setattr(wait_module, "list_windows", lambda include_hidden=False, query=None: [])
    with pytest.raises(DesktopControlError) as exc_info:
        wait_module.wait_for_window(query="missing", timeout_seconds=0.01, interval_seconds=0.01)
    assert exc_info.value.code == "wait_timeout"


def test_wait_for_element_returns_match(monkeypatch):
    monkeypatch.setattr(
        wait_module,
        "find_uia_elements",
        lambda hwnd, selector, max_depth=6, max_nodes=500: [{"name": "Apply"}],
    )
    result = wait_module.wait_for_element(100, {"name": "Apply"}, timeout_seconds=0.01, interval_seconds=0.01)
    assert result["ok"] is True
    assert result["element"]["name"] == "Apply"
