import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.models import Rect, WindowInfo
from desktop_control.policy import (
    APPROVALS_FILE_ENV,
    APPROVED_APPS_ENV,
    REQUIRE_APPROVALS_ENV,
    approve_process_name,
    approve_window,
    assert_allowed_target,
    load_approvals,
)


def window(process_name="notepad.exe", title="Untitled - Notepad", class_name="Notepad"):
    return WindowInfo(
        hwnd=100,
        title=title,
        process_id=10,
        process_name=process_name,
        class_name=class_name,
        rect=Rect(0, 0, 500, 400),
        visible=True,
        minimized=False,
        client_rect=Rect(8, 32, 492, 392),
    )


def test_allows_safe_notepad_window():
    assert_allowed_target(window(), "type_text")


def test_blocks_terminal_process():
    with pytest.raises(DesktopControlError) as exc_info:
        assert_allowed_target(window(process_name="pwsh.exe", title="PowerShell"), "type_text")
    assert exc_info.value.code == "policy_denied"


def test_blocks_sensitive_title():
    with pytest.raises(DesktopControlError):
        assert_allowed_target(window(title="Windows Security"), "click")


def test_requires_approval_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv(REQUIRE_APPROVALS_ENV, "1")
    monkeypatch.setenv(APPROVALS_FILE_ENV, str(tmp_path / "approvals.json"))
    monkeypatch.delenv(APPROVED_APPS_ENV, raising=False)

    with pytest.raises(DesktopControlError) as exc_info:
        assert_allowed_target(window(), "click")
    assert exc_info.value.code == "approval_required"


def test_allows_env_approved_app_when_required(monkeypatch, tmp_path):
    monkeypatch.setenv(REQUIRE_APPROVALS_ENV, "1")
    monkeypatch.setenv(APPROVALS_FILE_ENV, str(tmp_path / "approvals.json"))
    monkeypatch.setenv(APPROVED_APPS_ENV, "notepad.exe")

    assert_allowed_target(window(), "click")


def test_approval_file_allows_process_when_required(monkeypatch, tmp_path):
    approvals_path = tmp_path / "approvals.json"
    monkeypatch.setenv(REQUIRE_APPROVALS_ENV, "1")
    monkeypatch.setenv(APPROVALS_FILE_ENV, str(approvals_path))
    approve_process_name("notepad.exe", explicit_path=str(approvals_path))

    assert_allowed_target(window(), "click")
    assert load_approvals(str(approvals_path))["process_names"] == ["notepad.exe"]


def test_approve_window_allows_matching_window_when_required(monkeypatch, tmp_path):
    approvals_path = tmp_path / "approvals.json"
    monkeypatch.setenv(REQUIRE_APPROVALS_ENV, "1")
    monkeypatch.setenv(APPROVALS_FILE_ENV, str(approvals_path))
    approve_window(window(), explicit_path=str(approvals_path))

    assert_allowed_target(window(), "click")


def test_blocked_process_cannot_be_approved(tmp_path):
    with pytest.raises(DesktopControlError) as exc_info:
        approve_process_name("pwsh.exe", explicit_path=str(tmp_path / "approvals.json"))
    assert exc_info.value.code == "policy_denied"
