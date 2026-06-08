from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from .errors import DesktopControlError, wrap_os_error
from .models import WindowInfo
from .policy import assert_allowed_app_launch
from .wait import wait_for_window
from .windows import list_windows

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
shell32.ShellExecuteW.argtypes = (
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
)
shell32.ShellExecuteW.restype = ctypes.c_void_p
SW_SHOWNORMAL = 1


@dataclass
class AppInfo:
    id: str
    display_name: str
    source: str
    launch_path: str | None = None
    executable_path: str | None = None
    process_name: str | None = None
    running: bool = False
    process_ids: list[int] = field(default_factory=list)
    windows: list[WindowInfo] = field(default_factory=list)

    def app_ref(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "process_name": self.process_name,
            "executable_path": self.executable_path,
            "launch_path": self.launch_path,
        }

    def to_dict(self, include_windows: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "display_name": self.display_name,
            "source": self.source,
            "launch_path": self.launch_path,
            "executable_path": self.executable_path,
            "process_name": self.process_name,
            "running": self.running,
            "process_ids": sorted(set(self.process_ids)),
            "app_ref": self.app_ref(),
        }
        if include_windows:
            payload["windows"] = [window.to_dict() for window in self.windows]
        return payload


def _stable_app_id(*parts: object) -> str:
    payload = "|".join(str(part or "").casefold() for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _path_text(path: Path | str | None) -> str | None:
    if path is None:
        return None
    value = str(path).strip()
    return value or None


def _process_name_from_path(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("/", "\\").rsplit("\\", 1)[-1].lower() or None


def _app_key(app: AppInfo) -> str:
    return (
        (app.executable_path or "").casefold()
        or (app.process_name or "").casefold()
        or (app.launch_path or "").casefold()
        or app.display_name.casefold()
    )


def _merge_app(existing: AppInfo, incoming: AppInfo) -> AppInfo:
    sources = sorted(set(existing.source.split("+")) | set(incoming.source.split("+")))
    existing.source = "+".join(source for source in sources if source)
    existing.launch_path = existing.launch_path or incoming.launch_path
    existing.executable_path = existing.executable_path or incoming.executable_path
    existing.process_name = existing.process_name or incoming.process_name
    existing.running = existing.running or incoming.running
    existing.process_ids = sorted(set(existing.process_ids + incoming.process_ids))
    by_hwnd = {window.hwnd: window for window in existing.windows}
    by_hwnd.update({window.hwnd: window for window in incoming.windows})
    existing.windows = sorted(by_hwnd.values(), key=lambda window: window.hwnd)
    return existing


def _start_menu_directories() -> list[Path]:
    candidates = [
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    return [path for path in candidates if str(path) and path.exists()]


def _resolve_shortcut(shortcut_path: Path) -> tuple[str | None, str | None]:
    try:
        import win32com.client  # type: ignore[import-not-found]

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(shortcut_path))
        return _path_text(getattr(shortcut, "Targetpath", None)), _path_text(getattr(shortcut, "Arguments", None))
    except Exception:
        return None, None


def _start_menu_apps() -> list[AppInfo]:
    apps: list[AppInfo] = []
    for directory in _start_menu_directories():
        for shortcut_path in directory.rglob("*.lnk"):
            target_path, _arguments = _resolve_shortcut(shortcut_path)
            launch_path = str(shortcut_path)
            process_name = _process_name_from_path(target_path)
            display_name = shortcut_path.stem.strip()
            apps.append(
                AppInfo(
                    id=_stable_app_id("start_menu", launch_path, target_path, display_name),
                    display_name=display_name,
                    source="start_menu",
                    launch_path=launch_path,
                    executable_path=target_path,
                    process_name=process_name,
                )
            )
    return apps


def _process_executable(pid: int) -> str | None:
    try:
        return psutil.Process(pid).exe() or None
    except (psutil.Error, OSError):
        return None


def _running_apps(include_windows: bool = True) -> list[AppInfo]:
    windows_by_pid: dict[int, list[WindowInfo]] = {}
    for window in list_windows(include_hidden=False):
        windows_by_pid.setdefault(window.process_id, []).append(window)

    apps: list[AppInfo] = []
    for pid, windows in windows_by_pid.items():
        first = windows[0]
        executable_path = _process_executable(pid)
        process_name = first.process_name or _process_name_from_path(executable_path)
        display_name = (process_name or f"Process {pid}").removesuffix(".exe")
        apps.append(
            AppInfo(
                id=_stable_app_id("running", executable_path, process_name, display_name),
                display_name=display_name,
                source="running",
                launch_path=executable_path,
                executable_path=executable_path,
                process_name=process_name,
                running=True,
                process_ids=[pid],
                windows=windows if include_windows else [],
            )
        )
    return apps


def _matches_query(app: AppInfo, query: str | None) -> bool:
    if not query:
        return True
    query_lc = query.casefold()
    haystack = " ".join(
        value or ""
        for value in (
            app.id,
            app.display_name,
            app.process_name,
            app.executable_path,
            app.launch_path,
        )
    ).casefold()
    return query_lc in haystack


def list_apps(
    query: str | None = None,
    *,
    include_windows: bool = True,
    include_start_menu: bool = True,
    include_running: bool = True,
    limit: int | None = None,
) -> list[AppInfo]:
    merged: dict[str, AppInfo] = {}
    sources: list[AppInfo] = []
    if include_start_menu:
        sources.extend(_start_menu_apps())
    if include_running:
        sources.extend(_running_apps(include_windows=include_windows))

    for app in sources:
        if not _matches_query(app, query):
            continue
        key = _app_key(app)
        if key in merged:
            _merge_app(merged[key], app)
        else:
            merged[key] = app

    apps = sorted(
        merged.values(),
        key=lambda app: (not app.running, app.display_name.casefold(), app.process_name or "", app.id),
    )
    if limit is not None:
        apps = apps[: max(0, limit)]
    return apps


def find_app(app_selector: str) -> AppInfo | None:
    selector = app_selector.strip()
    if not selector:
        return None
    selector_lc = selector.casefold()
    candidates = list_apps(query=selector)
    exact_matches = [
        app
        for app in candidates
        if selector_lc
        in {
            app.id.casefold(),
            app.display_name.casefold(),
            (app.process_name or "").casefold(),
            (app.executable_path or "").casefold(),
            (app.launch_path or "").casefold(),
        }
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise DesktopControlError(
            "app_selection_ambiguous",
            "Multiple apps matched the requested app exactly",
            {"selector": app_selector, "matches": [app.to_dict(include_windows=False) for app in exact_matches[:8]]},
        )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise DesktopControlError(
            "app_selection_ambiguous",
            "Multiple apps matched the requested app",
            {"selector": app_selector, "matches": [app.to_dict(include_windows=False) for app in candidates[:8]]},
        )
    return None


def _shell_execute(file: str, args: list[str] | None = None, cwd: str | None = None) -> int:
    parameters = subprocess.list2cmdline(args or []) if args else None
    result = shell32.ShellExecuteW(None, "open", file, parameters, cwd, SW_SHOWNORMAL)
    return int(result or 0)


def _transient_app(app_selector: str) -> AppInfo:
    path = Path(app_selector)
    executable_path = str(path) if path.exists() else None
    process_name = _process_name_from_path(executable_path or app_selector)
    return AppInfo(
        id=_stable_app_id("transient", app_selector),
        display_name=path.stem if executable_path else app_selector,
        source="transient",
        launch_path=executable_path or app_selector,
        executable_path=executable_path,
        process_name=process_name,
    )


def launch_app(
    app_selector: str,
    *,
    args: list[str] | None = None,
    cwd: str | None = None,
    wait: bool = True,
    wait_query: str | None = None,
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.1,
) -> dict[str, Any]:
    app = find_app(app_selector) or _transient_app(app_selector)
    selector_path = Path(app_selector)
    if selector_path.exists():
        launch_target = str(selector_path)
    elif args and app.executable_path:
        launch_target = app.executable_path
    else:
        launch_target = app.launch_path or app.executable_path or app_selector
    assert_allowed_app_launch(
        app.display_name,
        process_name=app.process_name,
        executable_path=app.executable_path or launch_target,
    )

    started_at = time.time()
    try:
        shell_result = _shell_execute(launch_target, args=args, cwd=cwd)
    except Exception as exc:
        raise wrap_os_error("app_launch_failed", f"Could not launch app {app_selector}", exc) from exc
    if shell_result <= 32:
        raise DesktopControlError(
            "app_launch_failed",
            "Windows ShellExecute failed to launch the app",
            {"app": app_selector, "launch_target": launch_target, "shell_result": shell_result},
        )

    payload: dict[str, Any] = {
        "ok": True,
        "action": "launch_app",
        "app": app.to_dict(include_windows=False),
        "launch": {
            "target": launch_target,
            "args_count": len(args or []),
            "cwd": cwd,
            "shell_result": shell_result,
            "started_at": started_at,
        },
    }
    if wait:
        query = wait_query or app.process_name or app.display_name
        try:
            window_result = wait_for_window(
                query=query,
                timeout_seconds=timeout_seconds,
                interval_seconds=interval_seconds,
            )
        except DesktopControlError as exc:
            raise DesktopControlError(
                "app_launch_window_timeout",
                "App launched but no matching window appeared before timeout",
                {"app": app.to_dict(include_windows=False), "wait_query": query, "timeout_seconds": timeout_seconds},
            ) from exc
        payload["window"] = window_result["window"]
        payload["wait"] = {
            "query": query,
            "attempts": window_result["attempts"],
            "timeout_seconds": timeout_seconds,
        }
    return payload
