from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import DesktopControlError
from .models import WindowInfo

APPROVALS_FILE_ENV = "DESKTOP_CONTROL_APPROVALS_FILE"
APPROVED_APPS_ENV = "DESKTOP_CONTROL_APPROVED_APPS"
REQUIRE_APPROVALS_ENV = "DESKTOP_CONTROL_REQUIRE_APPROVALS"
POLICY_FILE_ENV = "DESKTOP_CONTROL_POLICY_FILE"
BLOCKED_PROCESSES_ENV = "DESKTOP_CONTROL_BLOCKED_PROCESSES"
BLOCKED_TITLE_TERMS_ENV = "DESKTOP_CONTROL_BLOCKED_TITLE_TERMS"
BLOCKED_CLASS_TERMS_ENV = "DESKTOP_CONTROL_BLOCKED_CLASS_TERMS"
DEFAULT_APPROVALS_FILE = ".tmp/desktop-control-approvals.json"

DEFAULT_BLOCKED_PROCESS_NAMES = {
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

DEFAULT_BLOCKED_TITLE_TERMS = {
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

DEFAULT_BLOCKED_CLASS_TERMS = {
    "credential",
}


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _split_env_list(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _list_config_values(data: dict[str, Any], key: str) -> set[str]:
    values = data.get(key, [])
    if not isinstance(values, list):
        raise DesktopControlError(
            "policy_config_invalid",
            f"Policy config field {key} must be a list",
            {"field": key},
        )
    return {str(item).strip().lower() for item in values if str(item).strip()}


def load_policy_config(explicit_path: str | None = None) -> dict[str, set[str]]:
    path_value = explicit_path or os.environ.get(POLICY_FILE_ENV)
    if not path_value:
        return {"blocked_process_names": set(), "blocked_title_terms": set(), "blocked_class_terms": set()}
    path = Path(path_value)
    if not path.exists():
        raise DesktopControlError("policy_config_missing", "Policy config file does not exist", {"path": str(path)})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesktopControlError(
            "policy_config_invalid",
            "Could not read desktop-control policy config",
            {"path": str(path), "exception": repr(exc)},
        ) from exc
    if not isinstance(data, dict):
        raise DesktopControlError("policy_config_invalid", "Policy config must be a JSON object", {"path": str(path)})
    return {
        "blocked_process_names": _list_config_values(data, "blocked_process_names"),
        "blocked_title_terms": _list_config_values(data, "blocked_title_terms"),
        "blocked_class_terms": _list_config_values(data, "blocked_class_terms"),
    }


def _effective_blocked_process_names() -> set[str]:
    return (
        set(DEFAULT_BLOCKED_PROCESS_NAMES)
        | _split_env_list(BLOCKED_PROCESSES_ENV)
        | load_policy_config()["blocked_process_names"]
    )


def _effective_blocked_title_terms() -> set[str]:
    return (
        set(DEFAULT_BLOCKED_TITLE_TERMS)
        | _split_env_list(BLOCKED_TITLE_TERMS_ENV)
        | load_policy_config()["blocked_title_terms"]
    )


def _effective_blocked_class_terms() -> set[str]:
    return (
        set(DEFAULT_BLOCKED_CLASS_TERMS)
        | _split_env_list(BLOCKED_CLASS_TERMS_ENV)
        | load_policy_config()["blocked_class_terms"]
    )


def approval_file_path(explicit_path: str | None = None, for_write: bool = False) -> Path | None:
    configured = explicit_path or os.environ.get(APPROVALS_FILE_ENV)
    if configured:
        return Path(configured)
    if for_write:
        return Path(DEFAULT_APPROVALS_FILE)
    return None


def _empty_approvals() -> dict[str, list[Any]]:
    return {"process_names": [], "windows": []}


def load_approvals(explicit_path: str | None = None) -> dict[str, list[Any]]:
    path = approval_file_path(explicit_path)
    if path is None or not path.exists():
        return _empty_approvals()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesktopControlError(
            "approval_store_invalid",
            "Could not read desktop-control approvals file",
            {"path": str(path), "exception": repr(exc)},
        ) from exc
    return {
        "process_names": list(data.get("process_names", [])),
        "windows": list(data.get("windows", [])),
    }


def save_approvals(approvals: dict[str, list[Any]], explicit_path: str | None = None) -> Path:
    path = approval_file_path(explicit_path, for_write=True)
    if path is None:
        raise DesktopControlError("approval_store_missing", "No approval file path is configured")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approvals, indent=2, sort_keys=True), encoding="utf-8")
    return path


def approve_process_name(process_name: str, explicit_path: str | None = None) -> dict[str, Any]:
    normalized = _process_basename(process_name)
    if not normalized:
        raise DesktopControlError("invalid_approval", "Process name cannot be empty")
    if _is_blocked_process_name(normalized):
        raise DesktopControlError(
            "policy_denied",
            "Refusing to approve a blocked process",
            {"process_name": process_name},
        )
    approvals = load_approvals(explicit_path)
    approved = {str(item).lower() for item in approvals["process_names"]}
    approved.add(normalized)
    approvals["process_names"] = sorted(approved)
    path = save_approvals(approvals, explicit_path)
    return {"ok": True, "approval_file": str(path), "process_name": normalized}


def approve_window(window: WindowInfo, explicit_path: str | None = None) -> dict[str, Any]:
    assert_not_blocked_target(window, "approve_window")
    approvals = load_approvals(explicit_path)
    entry = {
        "process_name": window.process_name.lower(),
        "title": window.title,
        "class_name": window.class_name,
    }
    existing = {
        json.dumps(item, sort_keys=True)
        for item in approvals["windows"]
        if isinstance(item, dict)
    }
    existing.add(json.dumps(entry, sort_keys=True))
    approvals["windows"] = [json.loads(item) for item in sorted(existing)]
    path = save_approvals(approvals, explicit_path)
    return {"ok": True, "approval_file": str(path), "window": window.to_dict(), "approval": entry}


def _process_basename(process_name_or_path: str) -> str:
    normalized = process_name_or_path.strip().replace("/", "\\")
    return normalized.rsplit("\\", 1)[-1].lower()


def _is_blocked_process_name(process_name: str) -> bool:
    candidates = {process_name}
    if "." not in process_name:
        candidates.add(f"{process_name}.exe")
    return bool(candidates & _effective_blocked_process_names())


def assert_not_blocked_process_name(process_name_or_path: str, action: str) -> None:
    process_name = _process_basename(process_name_or_path)
    if _is_blocked_process_name(process_name):
        raise DesktopControlError(
            "policy_denied",
            f"Refusing blocked process for action {action}",
            {"process_name": process_name_or_path},
        )


def assert_allowed_app_launch(
    app: str,
    *,
    process_name: str | None = None,
    executable_path: str | None = None,
) -> None:
    for candidate in (process_name, executable_path, app):
        if candidate:
            assert_not_blocked_process_name(candidate, "launch_app")

    app_lc = app.lower()
    matched_title = next((term for term in _effective_blocked_title_terms() if term in app_lc), None)
    if matched_title:
        raise DesktopControlError(
            "policy_denied",
            "Refusing to launch app with sensitive display name",
            {"matched_term": matched_title, "app": app},
        )


def is_approval_required() -> bool:
    return _truthy_env(REQUIRE_APPROVALS_ENV)


def is_window_approved(window: WindowInfo) -> bool:
    process_name = window.process_name.lower()
    if process_name in _split_env_list(APPROVED_APPS_ENV):
        return True

    approvals = load_approvals()
    approved_processes = {str(item).lower() for item in approvals["process_names"]}
    if process_name in approved_processes:
        return True

    for item in approvals["windows"]:
        if not isinstance(item, dict):
            continue
        approved_process = str(item.get("process_name", "")).lower()
        if approved_process and approved_process != process_name:
            continue
        approved_title = item.get("title")
        if approved_title is not None and str(approved_title) != window.title:
            continue
        approved_class = item.get("class_name")
        if approved_class is not None and str(approved_class) != window.class_name:
            continue
        return True

    return False


def assert_not_blocked_target(window: WindowInfo, action: str) -> None:
    process_name = window.process_name.lower()
    title = window.title.lower()
    class_name = window.class_name.lower()

    if process_name in _effective_blocked_process_names():
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate blocked process for action {action}",
            {"process_name": window.process_name, "hwnd": window.hwnd, "title": window.title},
        )

    matched_title = next((term for term in _effective_blocked_title_terms() if term in title), None)
    if matched_title:
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate sensitive window title for action {action}",
            {"matched_term": matched_title, "hwnd": window.hwnd, "title": window.title},
        )

    matched_class = next((term for term in _effective_blocked_class_terms() if term in class_name), None)
    if matched_class:
        raise DesktopControlError(
            "policy_denied",
            f"Refusing to automate sensitive window class for action {action}",
            {"matched_term": matched_class, "hwnd": window.hwnd, "class_name": window.class_name},
        )


def assert_allowed_target(window: WindowInfo, action: str) -> None:
    assert_not_blocked_target(window, action)
    if is_approval_required() and not is_window_approved(window):
        raise DesktopControlError(
            "approval_required",
            f"Target is not approved for action {action}",
            {
                "process_name": window.process_name,
                "hwnd": window.hwnd,
                "title": window.title,
                "approval_env": REQUIRE_APPROVALS_ENV,
                "approved_apps_env": APPROVED_APPS_ENV,
                "approvals_file_env": APPROVALS_FILE_ENV,
            },
        )

