from __future__ import annotations

from .errors import DesktopControlError
from .models import WindowInfo

BLOCKED_PROCESS_NAMES = {
    "cmd.exe",
    "codex.exe",
    "credentialuibroker.exe",
    "openai.exe",
    "powershell.exe",
    "pwsh.exe",
    "securityhealthsystray.exe",
    "terminal.exe",
    "windowsterminal.exe",
    "wt.exe",
}

BLOCKED_TITLE_TERMS = {
    "1password",
    "administrator:",
    "bitwarden",
    "credential",
    "credentials",
    "keychain",
    "lastpass",
    "passkey",
    "password",
    "security",
    "sign in",
    "uac",
    "user account control",
    "windows security",
}

BLOCKED_CLASS_TERMS = {
    "credential",
}


def assert_allowed_target(window: WindowInfo, action: str) -> None:
    process_name = window.process_name.lower()
    title = window.title.lower()
    class_name = window.class_name.lower()

    if process_name in BLOCKED_PROCESS_NAMES:
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate blocked process for action {action}",
            {"process_name": window.process_name, "hwnd": window.hwnd, "title": window.title},
        )

    matched_title = next((term for term in BLOCKED_TITLE_TERMS if term in title), None)
    if matched_title:
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate sensitive window title for action {action}",
            {"matched_term": matched_title, "hwnd": window.hwnd, "title": window.title},
        )

    matched_class = next((term for term in BLOCKED_CLASS_TERMS if term in class_name), None)
    if matched_class:
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate sensitive window class for action {action}",
            {"matched_term": matched_class, "hwnd": window.hwnd, "class_name": window.class_name},
        )

