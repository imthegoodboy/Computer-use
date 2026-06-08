import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.models import Rect, WindowInfo
from desktop_control.snapshot import assert_expected_snapshot, stable_snapshot_id


def window(title="Target", left=0):
    return WindowInfo(
        hwnd=100,
        title=title,
        process_id=10,
        process_name="target.exe",
        class_name="TargetWindow",
        rect=Rect(left, 0, left + 500, 400),
        visible=True,
        minimized=False,
        client_rect=Rect(left + 8, 32, left + 492, 392),
    )


def test_stable_snapshot_id_is_deterministic():
    payload = {"b": 2, "a": 1}
    assert stable_snapshot_id(payload) == stable_snapshot_id({"a": 1, "b": 2})


def test_window_snapshot_changes_when_geometry_changes():
    assert window(left=0).snapshot_id() != window(left=10).snapshot_id()


def test_window_dict_contains_snapshot_id():
    payload = window().to_dict()
    assert payload["snapshot_id"] == window().snapshot_id()


def test_expected_snapshot_accepts_match():
    snapshot_id = window().snapshot_id()
    assert_expected_snapshot(snapshot_id, snapshot_id)


def test_expected_snapshot_rejects_mismatch():
    with pytest.raises(DesktopControlError) as exc_info:
        assert_expected_snapshot("current", "expected")
    assert exc_info.value.code == "stale_snapshot"
