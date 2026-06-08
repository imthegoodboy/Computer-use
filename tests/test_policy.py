import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.models import Rect, WindowInfo
from desktop_control.policy import assert_allowed_target


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
