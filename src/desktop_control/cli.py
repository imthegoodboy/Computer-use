from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .apps import launch_app, list_apps
from .audit import record_audit_event
from .capture import capture_window
from .errors import DesktopControlError
from .input import click_at, drag_at, move_to, press_key_sequence, scroll_at, send_text
from .policy import approve_process_name, approve_window, assert_allowed_target, load_approvals
from .snapshot import assert_expected_snapshot
from .uia import click_uia_element, find_uia_elements, get_uia_tree, invoke_uia_element, set_uia_element_value
from .wait import wait_for_element, wait_for_window
from .windows import (
    CoordinateSpace,
    activate_window,
    get_window,
    list_windows,
    require_point_in_window,
    resolve_window_ref,
    resolve_point,
)


def _json_dump(payload: Any, pretty: bool) -> str:
    return json.dumps(payload, indent=2 if pretty else None, sort_keys=pretty)


def _print(payload: Any, pretty: bool) -> None:
    print(_json_dump(payload, pretty))


def _audit_params(args: argparse.Namespace) -> dict[str, Any]:
    params = vars(args).copy()
    params.pop("func", None)
    return params


def _space(value: str) -> CoordinateSpace:
    if value not in {"window", "client", "screen"}:
        raise argparse.ArgumentTypeError("space must be one of: window, client, screen")
    return value  # type: ignore[return-value]


def _window_for_action(hwnd: int, action: str, activate: bool = True):
    window = get_window(hwnd)
    assert_allowed_target(window, action)
    if activate:
        window = activate_window(hwnd)
        assert_allowed_target(window, action)
    return window


def _enforce_expected_snapshot(window, expected_snapshot_id: str | None) -> None:
    assert_expected_snapshot(window.snapshot_id(), expected_snapshot_id)


def _resolve_checked_point(hwnd: int, x: int, y: int, space: CoordinateSpace) -> tuple[int, int]:
    screen_x, screen_y = resolve_point(hwnd, x, y, space)
    require_point_in_window(hwnd, screen_x, screen_y)
    return screen_x, screen_y


def command_list_windows(args: argparse.Namespace) -> dict[str, Any]:
    windows = list_windows(include_hidden=args.include_hidden, query=args.query)
    return {
        "ok": True,
        "version": __version__,
        "windows": [window.to_dict() for window in windows],
    }


def command_list_apps(args: argparse.Namespace) -> dict[str, Any]:
    apps = list_apps(
        query=args.query,
        include_windows=not args.no_windows,
        include_start_menu=not args.no_start_menu,
        include_running=not args.no_running,
        limit=args.limit,
    )
    return {
        "ok": True,
        "version": __version__,
        "apps": [app.to_dict(include_windows=not args.no_windows) for app in apps],
    }


def command_launch_app(args: argparse.Namespace) -> dict[str, Any]:
    return launch_app(
        args.app,
        args=args.arg or [],
        cwd=args.cwd,
        wait=not args.no_wait,
        wait_query=args.wait_query,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
    )


def command_get_window(args: argparse.Namespace) -> dict[str, Any]:
    return {"ok": True, "window": get_window(args.window_id).to_dict()}


def command_activate_window(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "activate_window", activate=True)
    return {"ok": True, "action": "activate_window", "window": window.to_dict()}


def command_get_window_state(args: argparse.Namespace) -> dict[str, Any]:
    from .rpc import build_window_state

    params: dict[str, Any] = {
        "window_id": args.window_id,
        "include_screenshot": not args.no_screenshot,
        "include_text": args.include_text or args.include_ui,
        "max_depth": args.max_depth,
        "max_nodes": args.max_nodes,
        "screenshot_backend": args.screenshot_backend,
        "activate": args.activate,
    }
    if args.inline_screenshot:
        params["include_image_data"] = True
    if args.out:
        params["out"] = args.out
    return build_window_state(params, default_screenshot=True)


def _optional_window_ref_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    if getattr(args, "ref_file", None):
        payload = json.loads(Path(args.ref_file).read_text(encoding="utf-8-sig"))
        return _extract_window_ref_payload(payload)

    ref: dict[str, Any] = {}
    for arg_name, ref_name in (
        ("window_id", "hwnd"),
        ("process_id", "process_id"),
        ("process_name", "process_name"),
        ("title", "title"),
        ("title_contains", "title_contains"),
        ("class_name", "class_name"),
    ):
        value = getattr(args, arg_name, None)
        if value not in (None, ""):
            ref[ref_name] = value
    return ref or None


def command_observe(args: argparse.Namespace) -> dict[str, Any]:
    from .rpc import observe_window

    params: dict[str, Any] = {
        "include_screenshot": not args.no_screenshot,
        "include_text": args.include_text or args.include_ui,
        "max_depth": args.max_depth,
        "max_nodes": args.max_nodes,
        "screenshot_backend": args.screenshot_backend,
        "activate": args.activate,
        "include_hidden": args.include_hidden,
        "allow_ambiguous": args.allow_ambiguous,
    }
    if args.inline_screenshot:
        params["include_image_data"] = True
    if args.query:
        params["query"] = args.query
    if args.out:
        params["out"] = args.out
    ref = _optional_window_ref_from_args(args)
    if ref:
        params["window_ref"] = ref
    return observe_window(params)


def command_state(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "state", activate=args.activate)
    payload: dict[str, Any] = {
        "ok": True,
        "window": window.to_dict(),
    }
    if args.screenshot:
        payload["screenshot"] = capture_window(
            args.window_id,
            args.screenshot,
            backend=args.screenshot_backend,
            include_image_data=args.inline_screenshot,
        )
    if args.include_ui:
        payload["ui"] = get_uia_tree(args.window_id, max_depth=args.max_depth, max_nodes=args.max_nodes)
    return payload


def command_screenshot(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "screenshot", activate=args.activate)
    return {
        "ok": True,
        "window": window.to_dict(),
        "screenshot": capture_window(
            args.window_id,
            args.out,
            backend=args.backend,
            include_image_data=args.inline_screenshot,
        ),
    }


def command_click(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "click", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    click_at(x, y, button=args.button, count=args.count)
    return {
        "ok": True,
        "action": "click",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
        "button": args.button,
        "count": args.count,
    }


def command_double_click(args: argparse.Namespace) -> dict[str, Any]:
    args.count = 2
    return command_click(args)


def command_move(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "move", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    move_to(x, y)
    return {
        "ok": True,
        "action": "move",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
    }


def command_scroll(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "scroll", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    scroll_at(x, y, args.delta)
    return {
        "ok": True,
        "action": "scroll",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
        "delta": args.delta,
    }


def command_drag(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "drag", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    from_x, from_y = _resolve_checked_point(args.window_id, args.from_x, args.from_y, args.space)
    to_x, to_y = _resolve_checked_point(args.window_id, args.to_x, args.to_y, args.space)
    drag_at(
        from_x,
        from_y,
        to_x,
        to_y,
        button=args.button,
        duration_seconds=args.duration,
        steps=args.steps,
    )
    return {
        "ok": True,
        "action": "drag",
        "window": window.to_dict(),
        "from": {"x": from_x, "y": from_y},
        "to": {"x": to_x, "y": to_y},
        "button": args.button,
    }


def command_type_text(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "type_text", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    text = args.text
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    send_text(text, method=args.method)
    return {
        "ok": True,
        "action": "type_text",
        "window": window.to_dict(),
        "characters": len(text),
        "method": args.method,
    }


def command_key(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "key", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    press_key_sequence(args.keys)
    return {
        "ok": True,
        "action": "key",
        "window": window.to_dict(),
        "keys": args.keys,
    }


def _selector_from_args(args: argparse.Namespace) -> dict[str, Any]:
    selector: dict[str, Any] = {}
    for key in ("name", "name_contains", "automation_id", "class_name", "control_type"):
        value = getattr(args, key, None)
        if value is not None:
            selector[key] = value
    if getattr(args, "allow_multiple", False):
        selector["allow_multiple"] = True
    if getattr(args, "index", None) is not None:
        selector["index"] = args.index
    if not selector:
        raise DesktopControlError("invalid_selector", "At least one UIA selector field is required")
    return selector


def _extract_window_ref_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DesktopControlError("invalid_window_ref", "Window ref payload must be a JSON object")
    if isinstance(payload.get("window_ref"), dict):
        return dict(payload["window_ref"])
    if isinstance(payload.get("window"), dict):
        return _extract_window_ref_payload(payload["window"])
    return dict(payload)


def _window_ref_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.ref_file:
        payload = json.loads(Path(args.ref_file).read_text(encoding="utf-8-sig"))
        return _extract_window_ref_payload(payload)

    ref: dict[str, Any] = {}
    for arg_name, ref_name in (
        ("window_id", "hwnd"),
        ("process_id", "process_id"),
        ("process_name", "process_name"),
        ("title", "title"),
        ("title_contains", "title_contains"),
        ("class_name", "class_name"),
    ):
        value = getattr(args, arg_name, None)
        if value not in (None, ""):
            ref[ref_name] = value
    if not ref:
        raise DesktopControlError(
            "invalid_window_ref",
            "Use --ref-file or provide at least one direct window identity field",
        )
    return ref


def command_find_elements(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "find_elements", activate=False)
    selector = _selector_from_args(args)
    return {
        "ok": True,
        "window": window.to_dict(),
        "selector": selector,
        "elements": find_uia_elements(
            args.window_id,
            selector,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
        ),
    }


def command_click_element(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "click_element", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    result = click_uia_element(
        args.window_id,
        _selector_from_args(args),
        button=args.button,
        count=args.count,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
    )
    result["window"] = window.to_dict()
    return result


def command_invoke_element(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "invoke_element", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    result = invoke_uia_element(
        args.window_id,
        _selector_from_args(args),
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
    )
    result["window"] = window.to_dict()
    return result


def command_set_element_value(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "set_element_value", activate=not args.no_activate)
    _enforce_expected_snapshot(window, args.expect_snapshot_id)
    value = args.value
    if args.value_file:
        value = Path(args.value_file).read_text(encoding="utf-8")
    result = set_uia_element_value(
        args.window_id,
        _selector_from_args(args),
        value,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        fallback_text_method=args.fallback_text_method,
    )
    result["window"] = window.to_dict()
    return result


def command_wait_window(args: argparse.Namespace) -> dict[str, Any]:
    return wait_for_window(
        query=args.query,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
        include_hidden=args.include_hidden,
    )


def command_wait_element(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "wait_element", activate=False)
    result = wait_for_element(
        args.window_id,
        _selector_from_args(args),
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
    )
    result["window"] = window.to_dict()
    return result


def command_recover_window(args: argparse.Namespace) -> dict[str, Any]:
    window_ref = _window_ref_from_args(args)
    window = resolve_window_ref(
        window_ref,
        include_hidden=args.include_hidden,
        allow_ambiguous=args.allow_ambiguous,
    )
    return {
        "ok": True,
        "action": "recover_window",
        "input_ref": window_ref,
        "window": window.to_dict(),
    }


def command_approve_app(args: argparse.Namespace) -> dict[str, Any]:
    return approve_process_name(args.process_name, explicit_path=args.approvals_file)


def command_approve_window(args: argparse.Namespace) -> dict[str, Any]:
    window = get_window(args.window_id)
    return approve_window(window, explicit_path=args.approvals_file)


def command_list_approvals(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ok": True,
        "approval_file": args.approvals_file,
        "approvals": load_approvals(args.approvals_file),
    }


def command_batch(args: argparse.Namespace) -> dict[str, Any]:
    from .rpc import execute_batch_actions

    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    else:
        payload = json.loads(sys.stdin.read())

    if isinstance(payload, list):
        actions = payload
        stop_on_error = not args.continue_on_error
    elif isinstance(payload, dict):
        actions = payload.get("actions", [])
        stop_on_error = bool(payload.get("stop_on_error", not args.continue_on_error))
    else:
        raise DesktopControlError("invalid_request", "Batch payload must be a list or object")

    return execute_batch_actions(actions, stop_on_error=stop_on_error)


def _load_json_payload(file_path: str | None) -> Any:
    if file_path:
        return json.loads(Path(file_path).read_text(encoding="utf-8-sig"))
    return json.loads(sys.stdin.read())


def command_agent_step(args: argparse.Namespace) -> dict[str, Any]:
    from .rpc import execute_agent_step

    payload = _load_json_payload(args.file)
    if isinstance(payload, list):
        params: dict[str, Any] = {"actions": payload}
    elif isinstance(payload, dict):
        params = dict(payload)
    else:
        raise DesktopControlError("invalid_request", "agent-step payload must be a JSON object or array")

    if args.window_id is not None:
        params.setdefault("window_id", args.window_id)
    if args.query:
        params.setdefault("query", args.query)
    if args.ref_file:
        ref_payload = json.loads(Path(args.ref_file).read_text(encoding="utf-8-sig"))
        params.setdefault("window_ref", _extract_window_ref_payload(ref_payload))
    if args.expect_snapshot_id:
        params.setdefault("expect_snapshot_id", args.expect_snapshot_id)
    if args.space:
        params.setdefault("space", args.space)
    if args.continue_on_error:
        params["continue_on_error"] = True
    if args.observe_after:
        observe_after: dict[str, Any] = {}
        if args.include_text_after:
            observe_after["include_text"] = True
        if args.inline_screenshot_after:
            observe_after["include_image_data"] = True
        params["observe_after"] = observe_after or True
    return execute_agent_step(params)


def command_agent_run(args: argparse.Namespace) -> dict[str, Any]:
    from .rpc import execute_agent_run

    payload: Any = {}
    if args.file:
        payload = _load_json_payload(args.file)
    if isinstance(payload, list):
        params: dict[str, Any] = {"actions": payload}
    elif isinstance(payload, dict):
        params = dict(payload)
    else:
        raise DesktopControlError("invalid_request", "agent-run payload must be a JSON object or array")

    if args.window_id is not None:
        params.setdefault("window_id", args.window_id)
    if args.query:
        params.setdefault("query", args.query)
    if args.ref_file:
        ref_payload = json.loads(Path(args.ref_file).read_text(encoding="utf-8-sig"))
        params.setdefault("window_ref", _extract_window_ref_payload(ref_payload))
    if args.space:
        params.setdefault("space", args.space)
    if args.out:
        params.setdefault("out", args.out)
    if args.no_screenshot:
        params.setdefault("include_screenshot", False)
    if args.inline_screenshot:
        params["include_image_data"] = True
    if args.include_text or args.include_ui:
        params.setdefault("include_text", True)
    if args.include_text_after:
        params["include_text_after"] = True
    if args.continue_on_error:
        params["continue_on_error"] = True
    if args.no_observe_after:
        params["observe_after"] = False
    if args.screenshot_backend:
        params.setdefault("screenshot_backend", args.screenshot_backend)
    if args.activate:
        params.setdefault("activate", True)
    if args.allow_ambiguous:
        params.setdefault("allow_ambiguous", True)
    return execute_agent_run(params)


def command_serve_stdio(args: argparse.Namespace) -> int:
    from .rpc import serve_stdio

    return serve_stdio()


def command_serve_pipe(args: argparse.Namespace) -> int:
    from .pipe_transport import serve_pipe

    return serve_pipe(args.name)


def command_pipe_request(args: argparse.Namespace) -> dict[str, Any] | list[Any]:
    from .pipe_transport import pipe_request

    if args.request_file:
        payload = json.loads(Path(args.request_file).read_text(encoding="utf-8-sig"))
    else:
        payload = json.loads(sys.stdin.read())
    return pipe_request(args.name, payload, timeout_seconds=args.timeout)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop-control")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-windows", help="List visible top-level windows")
    list_parser.add_argument("--include-hidden", action="store_true")
    list_parser.add_argument("--query", help="Filter by title or process name")
    list_parser.add_argument("--pretty", action="store_true")
    list_parser.set_defaults(func=command_list_windows)

    apps_parser = subparsers.add_parser("list-apps", help="List launchable and running apps")
    apps_parser.add_argument("--query", help="Filter by app id, display name, process name, or path")
    apps_parser.add_argument("--no-windows", action="store_true", help="Do not include window payloads")
    apps_parser.add_argument("--no-start-menu", action="store_true", help="Skip Start Menu shortcuts")
    apps_parser.add_argument("--no-running", action="store_true", help="Skip running window-owning processes")
    apps_parser.add_argument("--limit", type=int)
    apps_parser.add_argument("--pretty", action="store_true")
    apps_parser.set_defaults(func=command_list_apps)

    launch_parser = subparsers.add_parser("launch-app", help="Launch an app by id, display name, process name, or path")
    launch_parser.add_argument("--app", required=True)
    launch_parser.add_argument("--arg", action="append", help="Argument passed to the launched app; repeat as needed")
    launch_parser.add_argument("--cwd")
    launch_parser.add_argument("--no-wait", action="store_true")
    launch_parser.add_argument("--wait-query", help="Window query to wait for after launch")
    launch_parser.add_argument("--timeout", type=float, default=10.0)
    launch_parser.add_argument("--interval", type=float, default=0.1)
    launch_parser.add_argument("--pretty", action="store_true")
    launch_parser.set_defaults(func=command_launch_app)

    get_window_parser = subparsers.add_parser("get-window", help="Get a current window object by id")
    get_window_parser.add_argument("--window-id", "--id", dest="window_id", type=int, required=True)
    get_window_parser.add_argument("--pretty", action="store_true")
    get_window_parser.set_defaults(func=command_get_window)

    activate_parser = subparsers.add_parser("activate-window", help="Activate and restore a target window")
    activate_parser.add_argument("--window-id", "--id", dest="window_id", type=int, required=True)
    activate_parser.add_argument("--pretty", action="store_true")
    activate_parser.set_defaults(func=command_activate_window)

    get_state_parser = subparsers.add_parser(
        "get-window-state",
        aliases=["get-state"],
        help="Get Codex-style window state with screenshot by default",
    )
    get_state_parser.add_argument("--window-id", "--id", dest="window_id", type=int, required=True)
    get_state_parser.add_argument("--out", help="Screenshot output path; defaults under DESKTOP_CONTROL_CAPTURE_DIR")
    get_state_parser.add_argument("--no-screenshot", action="store_true")
    get_state_parser.add_argument("--include-text", action="store_true")
    get_state_parser.add_argument("--include-ui", action="store_true", help="Alias for --include-text")
    get_state_parser.add_argument("--inline-screenshot", action="store_true", help="Embed screenshot as a data URL")
    get_state_parser.add_argument("--max-depth", type=int, default=3)
    get_state_parser.add_argument("--max-nodes", type=int, default=200)
    get_state_parser.add_argument("--screenshot-backend", choices=["auto", "pil", "mss"], default="auto")
    get_state_parser.add_argument("--activate", action="store_true")
    get_state_parser.add_argument("--pretty", action="store_true")
    get_state_parser.set_defaults(func=command_get_window_state)

    observe_parser = subparsers.add_parser(
        "observe",
        aliases=["view"],
        help="Select a window by query/ref/current foreground and return visual agent state",
    )
    observe_parser.add_argument("--window-id", "--id", dest="window_id", type=int)
    observe_parser.add_argument("--query", help="Select exactly one visible window by title or process name")
    observe_parser.add_argument("--ref-file", help="JSON file containing a window_ref, window, or full command result")
    observe_parser.add_argument("--process-id", type=int)
    observe_parser.add_argument("--process-name")
    observe_parser.add_argument("--title")
    observe_parser.add_argument("--title-contains")
    observe_parser.add_argument("--class-name")
    observe_parser.add_argument("--include-hidden", action="store_true")
    observe_parser.add_argument("--allow-ambiguous", action="store_true")
    observe_parser.add_argument("--out", help="Screenshot output path; defaults under DESKTOP_CONTROL_CAPTURE_DIR")
    observe_parser.add_argument("--no-screenshot", action="store_true")
    observe_parser.add_argument("--include-text", action="store_true")
    observe_parser.add_argument("--include-ui", action="store_true", help="Alias for --include-text")
    observe_parser.add_argument("--inline-screenshot", action="store_true", help="Embed screenshot as a data URL")
    observe_parser.add_argument("--max-depth", type=int, default=3)
    observe_parser.add_argument("--max-nodes", type=int, default=200)
    observe_parser.add_argument("--screenshot-backend", choices=["auto", "pil", "mss"], default="auto")
    observe_parser.add_argument("--activate", action="store_true")
    observe_parser.add_argument("--pretty", action="store_true")
    observe_parser.set_defaults(func=command_observe)

    state_parser = subparsers.add_parser("state", help="Get window state")
    state_parser.add_argument("--window-id", type=int, required=True)
    state_parser.add_argument("--include-ui", action="store_true")
    state_parser.add_argument("--inline-screenshot", action="store_true", help="Embed screenshot as a data URL")
    state_parser.add_argument("--max-depth", type=int, default=3)
    state_parser.add_argument("--max-nodes", type=int, default=200)
    state_parser.add_argument("--screenshot", help="Optional screenshot output path")
    state_parser.add_argument("--screenshot-backend", choices=["auto", "pil", "mss"], default="auto")
    state_parser.add_argument("--activate", action="store_true")
    state_parser.add_argument("--pretty", action="store_true")
    state_parser.set_defaults(func=command_state)

    screenshot_parser = subparsers.add_parser("screenshot", help="Capture a window screenshot")
    screenshot_parser.add_argument("--window-id", type=int, required=True)
    screenshot_parser.add_argument("--out", required=True)
    screenshot_parser.add_argument("--backend", choices=["auto", "pil", "mss"], default="auto")
    screenshot_parser.add_argument("--inline-screenshot", action="store_true", help="Embed screenshot as a data URL")
    screenshot_parser.add_argument("--activate", action="store_true")
    screenshot_parser.add_argument("--pretty", action="store_true")
    screenshot_parser.set_defaults(func=command_screenshot)

    click_parser = subparsers.add_parser("click", help="Click a window-relative point")
    click_parser.add_argument("--window-id", type=int, required=True)
    click_parser.add_argument("--x", type=int, required=True)
    click_parser.add_argument("--y", type=int, required=True)
    click_parser.add_argument("--space", type=_space, default="window")
    click_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    click_parser.add_argument("--count", type=int, default=1)
    click_parser.add_argument("--no-activate", action="store_true")
    click_parser.add_argument("--expect-snapshot-id")
    click_parser.add_argument("--pretty", action="store_true")
    click_parser.set_defaults(func=command_click)

    double_click_parser = subparsers.add_parser("double-click", help="Double-click a window-relative point")
    double_click_parser.add_argument("--window-id", type=int, required=True)
    double_click_parser.add_argument("--x", type=int, required=True)
    double_click_parser.add_argument("--y", type=int, required=True)
    double_click_parser.add_argument("--space", type=_space, default="window")
    double_click_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    double_click_parser.add_argument("--no-activate", action="store_true")
    double_click_parser.add_argument("--expect-snapshot-id")
    double_click_parser.add_argument("--pretty", action="store_true")
    double_click_parser.set_defaults(func=command_double_click)

    move_parser = subparsers.add_parser("move", help="Move the cursor to a window-relative point")
    move_parser.add_argument("--window-id", type=int, required=True)
    move_parser.add_argument("--x", type=int, required=True)
    move_parser.add_argument("--y", type=int, required=True)
    move_parser.add_argument("--space", type=_space, default="window")
    move_parser.add_argument("--no-activate", action="store_true")
    move_parser.add_argument("--expect-snapshot-id")
    move_parser.add_argument("--pretty", action="store_true")
    move_parser.set_defaults(func=command_move)

    scroll_parser = subparsers.add_parser("scroll", help="Scroll at a point")
    scroll_parser.add_argument("--window-id", type=int, required=True)
    scroll_parser.add_argument("--x", type=int, required=True)
    scroll_parser.add_argument("--y", type=int, required=True)
    scroll_parser.add_argument("--space", type=_space, default="window")
    scroll_parser.add_argument("--delta", type=int, required=True, help="Wheel ticks; positive scrolls up")
    scroll_parser.add_argument("--no-activate", action="store_true")
    scroll_parser.add_argument("--expect-snapshot-id")
    scroll_parser.add_argument("--pretty", action="store_true")
    scroll_parser.set_defaults(func=command_scroll)

    drag_parser = subparsers.add_parser("drag", help="Drag between two points")
    drag_parser.add_argument("--window-id", type=int, required=True)
    drag_parser.add_argument("--from-x", type=int, required=True)
    drag_parser.add_argument("--from-y", type=int, required=True)
    drag_parser.add_argument("--to-x", type=int, required=True)
    drag_parser.add_argument("--to-y", type=int, required=True)
    drag_parser.add_argument("--space", type=_space, default="window")
    drag_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    drag_parser.add_argument("--duration", type=float, default=0.2)
    drag_parser.add_argument("--steps", type=int, default=12)
    drag_parser.add_argument("--no-activate", action="store_true")
    drag_parser.add_argument("--expect-snapshot-id")
    drag_parser.add_argument("--pretty", action="store_true")
    drag_parser.set_defaults(func=command_drag)

    type_parser = subparsers.add_parser("type-text", aliases=["type"], help="Type text into a window")
    type_parser.add_argument("--window-id", type=int, required=True)
    type_parser.add_argument("--text", default="")
    type_parser.add_argument("--text-file")
    type_parser.add_argument("--method", choices=["clipboard", "unicode"], default="clipboard")
    type_parser.add_argument("--no-activate", action="store_true")
    type_parser.add_argument("--expect-snapshot-id")
    type_parser.add_argument("--pretty", action="store_true")
    type_parser.set_defaults(func=command_type_text)

    key_parser = subparsers.add_parser("key", aliases=["press-key", "keypress"], help="Press key chords")
    key_parser.add_argument("--window-id", type=int, required=True)
    key_parser.add_argument("--keys", action="append", required=True, help="Example: ctrl+a, enter, alt+f4")
    key_parser.add_argument("--no-activate", action="store_true")
    key_parser.add_argument("--expect-snapshot-id")
    key_parser.add_argument("--pretty", action="store_true")
    key_parser.set_defaults(func=command_key)

    def add_uia_selector_args(target_parser: argparse.ArgumentParser) -> None:
        target_parser.add_argument("--window-id", type=int, required=True)
        target_parser.add_argument("--name")
        target_parser.add_argument("--name-contains")
        target_parser.add_argument("--automation-id")
        target_parser.add_argument("--class-name")
        target_parser.add_argument("--control-type")
        target_parser.add_argument("--index", type=int)
        target_parser.add_argument("--allow-multiple", action="store_true")
        target_parser.add_argument("--max-depth", type=int, default=6)
        target_parser.add_argument("--max-nodes", type=int, default=500)
        target_parser.add_argument("--pretty", action="store_true")

    find_elements_parser = subparsers.add_parser("find-elements", help="Find UI Automation elements")
    add_uia_selector_args(find_elements_parser)
    find_elements_parser.set_defaults(func=command_find_elements)

    click_element_parser = subparsers.add_parser("click-element", help="Click the center of a UI Automation element")
    add_uia_selector_args(click_element_parser)
    click_element_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    click_element_parser.add_argument("--count", type=int, default=1)
    click_element_parser.add_argument("--no-activate", action="store_true")
    click_element_parser.add_argument("--expect-snapshot-id")
    click_element_parser.set_defaults(func=command_click_element)

    invoke_element_parser = subparsers.add_parser(
        "invoke-element",
        aliases=["perform-secondary-action"],
        help="Invoke a UI Automation element",
    )
    add_uia_selector_args(invoke_element_parser)
    invoke_element_parser.add_argument("--no-activate", action="store_true")
    invoke_element_parser.add_argument("--expect-snapshot-id")
    invoke_element_parser.set_defaults(func=command_invoke_element)

    set_element_parser = subparsers.add_parser(
        "set-element-value",
        aliases=["set-value"],
        help="Set a UI Automation element value",
    )
    add_uia_selector_args(set_element_parser)
    set_element_parser.add_argument("--value", default="")
    set_element_parser.add_argument("--value-file")
    set_element_parser.add_argument("--fallback-text-method", choices=["clipboard", "unicode"], default="clipboard")
    set_element_parser.add_argument("--no-activate", action="store_true")
    set_element_parser.add_argument("--expect-snapshot-id")
    set_element_parser.set_defaults(func=command_set_element_value)

    wait_window_parser = subparsers.add_parser("wait-window", help="Wait for a matching top-level window")
    wait_window_parser.add_argument("--query")
    wait_window_parser.add_argument("--timeout", type=float, default=10.0)
    wait_window_parser.add_argument("--interval", type=float, default=0.1)
    wait_window_parser.add_argument("--include-hidden", action="store_true")
    wait_window_parser.add_argument("--pretty", action="store_true")
    wait_window_parser.set_defaults(func=command_wait_window)

    wait_element_parser = subparsers.add_parser("wait-element", help="Wait for a matching UI Automation element")
    add_uia_selector_args(wait_element_parser)
    wait_element_parser.add_argument("--timeout", type=float, default=10.0)
    wait_element_parser.add_argument("--interval", type=float, default=0.1)
    wait_element_parser.set_defaults(func=command_wait_element)

    recover_parser = subparsers.add_parser("recover-window", help="Recover the current window from a saved window_ref")
    recover_parser.add_argument("--ref-file", help="JSON file containing a window_ref, window, or full command result")
    recover_parser.add_argument("--window-id", type=int, help="Known HWND to validate before fallback matching")
    recover_parser.add_argument("--process-id", type=int)
    recover_parser.add_argument("--process-name")
    recover_parser.add_argument("--title")
    recover_parser.add_argument("--title-contains")
    recover_parser.add_argument("--class-name")
    recover_parser.add_argument("--include-hidden", action="store_true")
    recover_parser.add_argument("--allow-ambiguous", action="store_true")
    recover_parser.add_argument("--pretty", action="store_true")
    recover_parser.set_defaults(func=command_recover_window)

    approve_app_parser = subparsers.add_parser("approve-app", help="Approve a process name for controlled actions")
    approve_app_parser.add_argument("--process-name", required=True)
    approve_app_parser.add_argument("--approvals-file")
    approve_app_parser.add_argument("--pretty", action="store_true")
    approve_app_parser.set_defaults(func=command_approve_app)

    approve_window_parser = subparsers.add_parser("approve-window", help="Approve the current process/title/class of a window")
    approve_window_parser.add_argument("--window-id", type=int, required=True)
    approve_window_parser.add_argument("--approvals-file")
    approve_window_parser.add_argument("--pretty", action="store_true")
    approve_window_parser.set_defaults(func=command_approve_window)

    approvals_parser = subparsers.add_parser("list-approvals", help="List configured desktop-control approvals")
    approvals_parser.add_argument("--approvals-file")
    approvals_parser.add_argument("--pretty", action="store_true")
    approvals_parser.set_defaults(func=command_list_approvals)

    batch_parser = subparsers.add_parser("batch", help="Run multiple desktop-control actions from JSON")
    batch_parser.add_argument("--file", help="JSON file containing an action list or {actions: [...]}")
    batch_parser.add_argument("--continue-on-error", action="store_true")
    batch_parser.add_argument("--pretty", action="store_true")
    batch_parser.set_defaults(func=command_batch)

    agent_step_parser = subparsers.add_parser(
        "agent-step",
        aliases=["act", "perform-actions"],
        help="Run OpenAI/Codex-style computer-use action JSON against a target window",
    )
    agent_step_parser.add_argument("--file", help="JSON object/array of computer-use actions; stdin when omitted")
    agent_step_parser.add_argument("--window-id", "--id", dest="window_id", type=int)
    agent_step_parser.add_argument("--query", help="Resolve the target window by title or process name")
    agent_step_parser.add_argument("--ref-file", help="JSON file containing a window_ref, window, or full observe result")
    agent_step_parser.add_argument("--expect-snapshot-id")
    agent_step_parser.add_argument("--space", choices=["window", "client", "screen"])
    agent_step_parser.add_argument("--continue-on-error", action="store_true")
    agent_step_parser.add_argument("--observe-after", action="store_true")
    agent_step_parser.add_argument("--include-text-after", action="store_true")
    agent_step_parser.add_argument("--inline-screenshot-after", action="store_true", help="Embed observe-after screenshot as a data URL")
    agent_step_parser.add_argument("--pretty", action="store_true")
    agent_step_parser.set_defaults(func=command_agent_step)

    agent_run_parser = subparsers.add_parser(
        "agent-run",
        aliases=["run"],
        help="Observe, run optional agent actions, and return the next visual state",
    )
    agent_run_parser.add_argument("--file", help="JSON object/array containing observe and action fields")
    agent_run_parser.add_argument("--window-id", "--id", dest="window_id", type=int)
    agent_run_parser.add_argument("--query", help="Resolve the target window by title or process name")
    agent_run_parser.add_argument("--ref-file", help="JSON file containing a window_ref, window, or full observe result")
    agent_run_parser.add_argument("--space", choices=["window", "client", "screen"])
    agent_run_parser.add_argument("--out", help="Initial screenshot output path; defaults under DESKTOP_CONTROL_CAPTURE_DIR")
    agent_run_parser.add_argument("--no-screenshot", action="store_true")
    agent_run_parser.add_argument("--include-text", action="store_true")
    agent_run_parser.add_argument("--include-ui", action="store_true", help="Alias for --include-text")
    agent_run_parser.add_argument("--inline-screenshot", action="store_true", help="Embed screenshots as data URLs")
    agent_run_parser.add_argument("--include-text-after", action="store_true")
    agent_run_parser.add_argument("--continue-on-error", action="store_true")
    agent_run_parser.add_argument("--no-observe-after", action="store_true")
    agent_run_parser.add_argument("--screenshot-backend", choices=["auto", "pil", "mss"], default="auto")
    agent_run_parser.add_argument("--activate", action="store_true")
    agent_run_parser.add_argument("--allow-ambiguous", action="store_true")
    agent_run_parser.add_argument("--pretty", action="store_true")
    agent_run_parser.set_defaults(func=command_agent_run)

    serve_parser = subparsers.add_parser("serve-stdio", help="Run JSON-RPC over stdin/stdout")
    serve_parser.set_defaults(func=command_serve_stdio)

    serve_pipe_parser = subparsers.add_parser("serve-pipe", help="Run length-prefixed JSON-RPC over a Windows named pipe")
    serve_pipe_parser.add_argument("--name", required=True, help="Simple pipe name or full \\\\.\\pipe\\ path")
    serve_pipe_parser.set_defaults(func=command_serve_pipe)

    pipe_request_parser = subparsers.add_parser("pipe-request", help="Send one framed JSON-RPC request to serve-pipe")
    pipe_request_parser.add_argument("--name", required=True, help="Simple pipe name or full \\\\.\\pipe\\ path")
    pipe_request_parser.add_argument("--request-file")
    pipe_request_parser.add_argument("--timeout", type=float, default=10.0)
    pipe_request_parser.add_argument("--pretty", action="store_true")
    pipe_request_parser.set_defaults(func=command_pipe_request)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        if isinstance(payload, int):
            return payload
        record_audit_event("cli", getattr(args, "command", None), _audit_params(args), result=payload)
        _print(payload, pretty=bool(getattr(args, "pretty", False)))
        return 0
    except DesktopControlError as exc:
        record_audit_event("cli", getattr(args, "command", None), _audit_params(args), error=exc.to_dict()["error"])
        print(_json_dump(exc.to_dict(), pretty=True), file=sys.stderr)
        return 2
