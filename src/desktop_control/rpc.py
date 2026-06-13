from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .apps import launch_app, list_apps
from .audit import record_audit_event
from .capture import capture_window, default_capture_path
from .cli import _resolve_checked_point, _window_for_action
from .errors import DesktopControlError
from .input import click_at, drag_at, move_to, press_key_sequence, scroll_at, send_text
from .snapshot import assert_expected_snapshot
from .uia import click_uia_element, find_uia_elements, get_uia_tree, invoke_uia_element, set_uia_element_value
from .wait import wait_for_element, wait_for_window
from .windows import get_foreground_window, get_window, list_windows, resolve_window_ref


def _rpc_success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data:
        payload["error"]["data"] = data
    return payload


def _require(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise DesktopControlError("invalid_request", f"Missing required parameter: {key}")
    return params[key]


def _window_id_from_params(params: dict[str, Any]) -> int:
    raw_window = params.get("window")
    if isinstance(raw_window, dict):
        for key in ("hwnd", "id", "window_id"):
            value = raw_window.get(key)
            if value not in (None, ""):
                return int(value)
    for key in ("window_id", "hwnd", "id"):
        value = params.get(key)
        if value not in (None, ""):
            return int(value)
    raise DesktopControlError("invalid_request", "Missing required parameter: window_id")


def _selector_from_params(params: dict[str, Any]) -> dict[str, Any]:
    raw_selector = params.get("selector")
    if isinstance(raw_selector, dict):
        selector = dict(raw_selector)
    else:
        selector = {}
        for key in (
            "name",
            "name_contains",
            "automation_id",
            "class_name",
            "control_type",
            "index",
            "allow_multiple",
        ):
            if key in params:
                selector[key] = params[key]
        if "element_index" in params:
            selector["index"] = params["element_index"]
            selector.setdefault("allow_multiple", True)
    if not selector:
        raise DesktopControlError("invalid_selector", "At least one UIA selector field is required")
    return selector


def _capture_output_path(hwnd: int, params: dict[str, Any]) -> str:
    for key in ("out", "screenshot_path", "path"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value
    screenshot_value = params.get("screenshot")
    if isinstance(screenshot_value, str) and screenshot_value.strip():
        return screenshot_value
    return str(default_capture_path(hwnd))


def _include_screenshot(params: dict[str, Any], default: bool) -> bool:
    if "include_screenshot" in params:
        return bool(params["include_screenshot"])
    screenshot_value = params.get("screenshot")
    if isinstance(screenshot_value, bool):
        return screenshot_value
    if isinstance(screenshot_value, str) and screenshot_value.strip():
        return True
    return default


def _screenshot_payload(hwnd: int, params: dict[str, Any]) -> dict[str, Any]:
    screenshot = capture_window(
        hwnd,
        _capture_output_path(hwnd, params),
        backend=params.get("screenshot_backend", params.get("backend", "auto")),
    )
    image = screenshot.get("image")
    digest = image.get("sha256", "") if isinstance(image, dict) else ""
    screenshot_id = f"shot-{str(digest)[:16]}" if digest else f"shot-{screenshot.get('window_snapshot_id', hwnd)}"
    return {"id": screenshot_id, **screenshot}


def build_window_state(params: dict[str, Any], *, default_screenshot: bool = True) -> dict[str, Any]:
    hwnd = _window_id_from_params(params)
    include_screenshot = _include_screenshot(params, default=default_screenshot)
    include_text = bool(params.get("include_text", params.get("include_ui", False)))
    if not include_screenshot and not include_text:
        raise DesktopControlError(
            "invalid_request",
            "Window state must include at least one of screenshot or UI text",
        )

    activate = bool(params.get("activate", False))
    window = _window_for_action(hwnd, "get_window_state", activate=activate)
    settle_ms = int(params.get("settle_ms", 0) or 0)
    if activate and settle_ms > 0:
        time.sleep(min(settle_ms, 2000) / 1000.0)
        window = _window_for_action(hwnd, "get_window_state", activate=False)
    result: dict[str, Any] = {
        "ok": True,
        "action": "get_window_state",
        "window": window.to_dict(),
        "generation": window.snapshot_id(),
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "screenshots": [],
    }
    if include_screenshot:
        result["screenshots"].append(_screenshot_payload(hwnd, params))
    if include_text:
        result["accessibility"] = get_uia_tree(
            hwnd,
            max_depth=int(params.get("max_depth", 3)),
            max_nodes=int(params.get("max_nodes", 200)),
        )
    return result


def _window_summary(window) -> dict[str, Any]:
    return {
        "id": window.hwnd,
        "hwnd": window.hwnd,
        "app": window.process_name,
        "title": window.title,
        "process_id": window.process_id,
        "process_name": window.process_name,
        "class_name": window.class_name,
        "snapshot_id": window.snapshot_id(),
    }


def _select_observe_window(params: dict[str, Any]):
    include_hidden = bool(params.get("include_hidden", False))
    allow_ambiguous = bool(params.get("allow_ambiguous", False))
    raw_ref = params.get("window_ref")
    raw_window = params.get("window")

    if isinstance(raw_ref, dict):
        window = resolve_window_ref(raw_ref, include_hidden=include_hidden, allow_ambiguous=allow_ambiguous)
        return window, {"source": "window_ref", "window_ref": dict(raw_ref)}

    if isinstance(raw_window, dict):
        ref = {}
        for source_key, ref_key in (
            ("hwnd", "hwnd"),
            ("id", "hwnd"),
            ("window_id", "hwnd"),
            ("process_id", "process_id"),
            ("process_name", "process_name"),
            ("app", "process_name"),
            ("title", "title"),
            ("class_name", "class_name"),
        ):
            value = raw_window.get(source_key)
            if value not in (None, ""):
                ref[ref_key] = value
        if ref:
            window = resolve_window_ref(ref, include_hidden=include_hidden, allow_ambiguous=allow_ambiguous)
            return window, {"source": "window", "window_ref": ref}

    for key in ("window_id", "hwnd", "id"):
        value = params.get(key)
        if value not in (None, ""):
            window = get_window(int(value))
            return window, {"source": key}

    query = params.get("query")
    if isinstance(query, str) and query.strip():
        matches = list_windows(include_hidden=include_hidden, query=query)
        if not matches:
            raise DesktopControlError(
                "window_not_found",
                "No window matched the observe query",
                {"query": query, "include_hidden": include_hidden},
            )
        if len(matches) > 1 and not allow_ambiguous:
            raise DesktopControlError(
                "ambiguous_window",
                "Multiple windows matched the observe query",
                {"query": query, "matches": [_window_summary(window) for window in matches[:8]]},
            )
        return matches[0], {
            "source": "query",
            "query": query,
            "match_count": len(matches),
        }

    window = get_foreground_window()
    return window, {"source": "foreground"}


def observe_window(params: dict[str, Any]) -> dict[str, Any]:
    window, selection = _select_observe_window(params)
    state_params = {
        key: value
        for key, value in params.items()
        if key
        not in {
            "active",
            "allow_ambiguous",
            "include_hidden",
            "query",
            "window",
            "window_ref",
        }
    }
    state_params["window_id"] = window.hwnd
    state = build_window_state(state_params, default_screenshot=True)
    state["action"] = "observe"
    state["selection"] = selection
    return state


def _normalize_method_and_params(method: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    normalized = method
    next_params = dict(params)
    aliases = {
        "keypress": "key",
        "press_key": "key",
        "type": "type_text",
        "set_value": "set_element_value",
        "perform_secondary_action": "invoke_element",
        "view": "observe",
    }
    normalized = aliases.get(normalized, normalized)
    if method == "double_click":
        normalized = "click"
        next_params.setdefault("count", 2)
    return normalized, next_params


def execute_batch_actions(actions: list[Any], stop_on_error: bool = True) -> dict[str, Any]:
    if not isinstance(actions, list) or not actions:
        raise DesktopControlError("invalid_request", "Batch actions must be a non-empty list")

    results: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            error = {
                "code": "invalid_request",
                "message": "Batch action must be an object",
                "details": {"index": index},
            }
            results.append({"ok": False, "index": index, "method": None, "error": error})
            if stop_on_error:
                raise DesktopControlError("batch_action_failed", "Batch action failed", {"failed_index": index, "results": results})
            continue

        method = action.get("method")
        params = action.get("params", {})
        if not isinstance(method, str):
            error = {
                "code": "invalid_request",
                "message": "Batch action method must be a string",
                "details": {"index": index},
            }
            results.append({"ok": False, "index": index, "method": method, "error": error})
            if stop_on_error:
                raise DesktopControlError("batch_action_failed", "Batch action failed", {"failed_index": index, "results": results})
            continue
        if method == "batch":
            error = {
                "code": "invalid_request",
                "message": "Nested batch actions are not supported",
                "details": {"index": index},
            }
            results.append({"ok": False, "index": index, "method": method, "error": error})
            if stop_on_error:
                raise DesktopControlError("batch_action_failed", "Batch action failed", {"failed_index": index, "results": results})
            continue
        if not isinstance(params, dict):
            error = {
                "code": "invalid_request",
                "message": "Batch action params must be an object",
                "details": {"index": index},
            }
            results.append({"ok": False, "index": index, "method": method, "error": error})
            if stop_on_error:
                raise DesktopControlError("batch_action_failed", "Batch action failed", {"failed_index": index, "results": results})
            continue

        try:
            result = _handle_method(method, params)
            results.append({"ok": True, "index": index, "method": method, "result": result})
        except DesktopControlError as exc:
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
            results.append({"ok": False, "index": index, "method": method, "error": error})
            if stop_on_error:
                raise DesktopControlError(
                    "batch_action_failed",
                    f"Batch action {index} failed",
                    {"failed_index": index, "results": results},
                ) from exc

    return {
        "ok": all(result["ok"] for result in results),
        "action": "batch",
        "count": len(results),
        "results": results,
    }


def _agent_step_actions(params: dict[str, Any]) -> list[Any]:
    if "actions" in params:
        actions = params["actions"]
        if isinstance(actions, dict):
            return [actions]
        if isinstance(actions, list):
            return actions
        raise DesktopControlError("invalid_request", "agent_step actions must be a list or object")

    action = params.get("action")
    if isinstance(action, dict):
        return [action]
    if any(key in params for key in ("type", "method")):
        return [params]
    raise DesktopControlError("invalid_request", "agent_step requires actions, action, type, or method")


def _has_agent_actions(params: dict[str, Any]) -> bool:
    return "actions" in params or "action" in params or any(key in params for key in ("type", "method"))


def _agent_window_context(params: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    raw_window = params.get("window")
    if isinstance(raw_window, dict):
        context["window"] = dict(raw_window)

    for key in ("window_id", "hwnd", "id"):
        value = params.get(key)
        if value not in (None, ""):
            context["window"] = {"id": int(value), "hwnd": int(value)}
            break

    if "window" not in context and any(
        params.get(key) not in (None, "")
        for key in ("window_ref", "query", "process_id", "process_name", "title", "title_contains", "class_name")
    ):
        window, _selection = _select_observe_window(params)
        context["window"] = window.to_dict()

    raw_context_window = context.get("window")
    snapshot_id = params.get("expect_snapshot_id", params.get("snapshot_id"))
    if snapshot_id is None and isinstance(raw_context_window, dict):
        snapshot_id = raw_context_window.get("snapshot_id")
    if snapshot_id not in (None, ""):
        context["expect_snapshot_id"] = str(snapshot_id)

    if params.get("space"):
        context["space"] = str(params["space"])
    if params.get("activate") is not None:
        context["activate"] = bool(params["activate"])
    return context


def _point_from_agent_value(value: Any, label: str) -> tuple[int, int]:
    if isinstance(value, dict):
        if "x" not in value or "y" not in value:
            raise DesktopControlError("invalid_request", f"{label} point must include x and y")
        return int(value["x"]), int(value["y"])
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return int(value[0]), int(value[1])
    raise DesktopControlError("invalid_request", f"{label} point must be an object or [x, y] array")


def _flatten_agent_action(action: dict[str, Any]) -> dict[str, Any]:
    nested = action.get("action")
    if isinstance(nested, dict) and "method" not in action and "type" not in action:
        flattened = dict(nested)
        for key in (
            "window",
            "window_id",
            "hwnd",
            "id",
            "expect_snapshot_id",
            "snapshot_id",
            "space",
            "activate",
        ):
            if key in action:
                flattened.setdefault(key, action[key])
        return flattened
    return dict(action)


def normalize_agent_action(action: Any, context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise DesktopControlError("invalid_request", "Agent action must be an object")

    source = _flatten_agent_action(action)
    raw_method = source.get("method", source.get("type", source.get("action")))
    if not isinstance(raw_method, str) or not raw_method.strip():
        raise DesktopControlError("invalid_request", "Agent action must include method, type, or action")
    method = raw_method.strip()

    params = {
        key: value
        for key, value in source.items()
        if key not in {"method", "type", "action"}
    }

    if method == "type":
        method = "type_text"
    elif method == "screenshot":
        method = "observe"
        params.setdefault("include_screenshot", True)

    if "mouse_button" in params and "button" not in params:
        params["button"] = params["mouse_button"]
    if "click_count" in params and "count" not in params:
        params["count"] = params["click_count"]
    if "screenshotId" in params and "screenshot_id" not in params:
        params["screenshot_id"] = params["screenshotId"]

    if method == "drag" and "path" in params:
        path = params.pop("path")
        if not isinstance(path, list) or len(path) < 2:
            raise DesktopControlError("invalid_request", "drag path must contain at least two points")
        from_x, from_y = _point_from_agent_value(path[0], "drag start")
        to_x, to_y = _point_from_agent_value(path[-1], "drag end")
        params.setdefault("from_x", from_x)
        params.setdefault("from_y", from_y)
        params.setdefault("to_x", to_x)
        params.setdefault("to_y", to_y)

    if "window" not in params and "window_id" not in params and "window" in context:
        params["window"] = context["window"]
    if "space" not in params and "space" in context:
        params["space"] = context["space"]
    if "activate" not in params and "activate" in context:
        params["activate"] = context["activate"]

    strict_snapshot = bool(context.get("strict_snapshot", True))
    if strict_snapshot and "expect_snapshot_id" not in params and "expect_snapshot_id" in context:
        if method in {"click", "double_click", "move", "scroll", "drag", "type_text", "key", "keypress", "press_key"}:
            params["expect_snapshot_id"] = context["expect_snapshot_id"]

    return {"method": method, "params": params}


def _agent_step_observe_after(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    raw_observe = params.get("observe_after", params.get("verify", False))
    if not raw_observe:
        return None
    observe_params = dict(raw_observe) if isinstance(raw_observe, dict) else {}
    if "window" not in observe_params and "window_id" not in observe_params and "window" in context:
        observe_params["window"] = context["window"]
    if params.get("include_text_after") is not None:
        observe_params["include_text"] = bool(params["include_text_after"])
    return observe_window(observe_params)


def execute_agent_step(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise DesktopControlError("invalid_request", "agent_step params must be an object")

    context = _agent_window_context(params)
    context["strict_snapshot"] = bool(params.get("strict_snapshot", True))
    actions = [normalize_agent_action(action, context) for action in _agent_step_actions(params)]
    stop_on_error = bool(params.get("stop_on_error", not bool(params.get("continue_on_error", False))))
    batch = execute_batch_actions(actions, stop_on_error=stop_on_error)
    result: dict[str, Any] = {
        "ok": batch["ok"],
        "action": "agent_step",
        "count": len(actions),
        "actions": actions,
        "batch": batch,
    }
    observation = _agent_step_observe_after(params, context)
    if observation is not None:
        result["observation"] = observation
    return result


def _elapsed_ms(start: float) -> int:
    return max(0, round((time.perf_counter() - start) * 1000))


def _agent_run_observe_params(params: dict[str, Any]) -> dict[str, Any] | None:
    raw_observe = params.get("observe", params.get("observation", True))
    if raw_observe is False:
        return None

    observe_params = dict(raw_observe) if isinstance(raw_observe, dict) else {}
    for key in (
        "window",
        "window_ref",
        "window_id",
        "hwnd",
        "id",
        "query",
        "process_id",
        "process_name",
        "title",
        "title_contains",
        "class_name",
        "include_hidden",
        "allow_ambiguous",
        "include_screenshot",
        "screenshot",
        "include_text",
        "include_ui",
        "max_depth",
        "max_nodes",
        "screenshot_backend",
        "backend",
        "out",
        "activate",
        "settle_ms",
    ):
        if key in params and key not in observe_params:
            observe_params[key] = params[key]
    return observe_params


def _agent_context_from_observation(observation: dict[str, Any] | None) -> dict[str, Any]:
    if not observation:
        return {}
    window = observation.get("window")
    if not isinstance(window, dict):
        return {}
    context = {"window": window}
    snapshot_id = window.get("snapshot_id") or observation.get("generation")
    if snapshot_id not in (None, ""):
        context["expect_snapshot_id"] = str(snapshot_id)
    return context


def _merge_agent_context(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    merged = dict(params)
    if "window" in context and "window" not in merged and "window_id" not in merged:
        merged["window"] = context["window"]
    if "expect_snapshot_id" in context and "expect_snapshot_id" not in merged and "snapshot_id" not in merged:
        merged["expect_snapshot_id"] = context["expect_snapshot_id"]
    return merged


def _agent_run_observe_after_params(
    params: dict[str, Any],
    observation: dict[str, Any] | None,
    has_actions: bool,
) -> dict[str, Any] | None:
    raw_observe = params.get("observe_after", params.get("verify", has_actions))
    if not raw_observe:
        return None

    observe_params = dict(raw_observe) if isinstance(raw_observe, dict) else {}
    window = observation.get("window") if isinstance(observation, dict) else None
    if isinstance(window, dict) and "window" not in observe_params and "window_id" not in observe_params:
        observe_params["window"] = window
    if params.get("include_text_after") is not None:
        observe_params["include_text"] = bool(params["include_text_after"])
    return observe_params


def execute_agent_run(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise DesktopControlError("invalid_request", "agent_run params must be an object")

    trace: list[dict[str, Any]] = []
    run_start = time.perf_counter()
    observation: dict[str, Any] | None = None

    has_actions = _has_agent_actions(params)
    observe_params = _agent_run_observe_params(params)
    if has_actions and observe_params is not None and "activate" not in observe_params:
        observe_params["activate"] = True
    if has_actions and observe_params is not None and "settle_ms" not in observe_params:
        observe_params["settle_ms"] = 150
    if observe_params is not None:
        started = time.perf_counter()
        observation = observe_window(observe_params)
        trace.append(
            {
                "phase": "observe",
                "elapsed_ms": _elapsed_ms(started),
                "snapshot_id": observation.get("generation"),
            }
        )

    step: dict[str, Any] | None = None
    if has_actions:
        started = time.perf_counter()
        step_params = _merge_agent_context(params, _agent_context_from_observation(observation))
        step_params.setdefault("strict_snapshot", False)
        step_params["observe_after"] = False
        step = execute_agent_step(step_params)
        trace.append({"phase": "act", "elapsed_ms": _elapsed_ms(started), "count": step.get("count", 0)})

    next_observation: dict[str, Any] | None = None
    observe_after_params = _agent_run_observe_after_params(params, observation, has_actions)
    if observe_after_params is not None:
        started = time.perf_counter()
        next_observation = observe_window(observe_after_params)
        trace.append(
            {
                "phase": "observe_after",
                "elapsed_ms": _elapsed_ms(started),
                "snapshot_id": next_observation.get("generation"),
            }
        )

    current_observation = next_observation or observation
    result: dict[str, Any] = {
        "ok": bool(step["ok"]) if step is not None else True,
        "action": "agent_run",
        "elapsed_ms": _elapsed_ms(run_start),
        "trace": trace,
    }
    if observation is not None:
        result["observation"] = observation
    if step is not None:
        result["step"] = step
    if next_observation is not None:
        result["next_observation"] = next_observation
    if current_observation is not None:
        result["current_observation"] = current_observation
    return result


def _enforce_expected_snapshot(window, params: dict[str, Any]) -> None:
    expected = params.get("expect_snapshot_id")
    assert_expected_snapshot(window.snapshot_id(), str(expected) if expected is not None else None)


def _handle_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
    method, params = _normalize_method_and_params(method, params)

    if method == "batch":
        return execute_batch_actions(
            params.get("actions", []),
            stop_on_error=bool(params.get("stop_on_error", True)),
        )

    if method in {"agent_step", "act", "perform_actions"}:
        return execute_agent_step(params)

    if method in {"agent_run", "run"}:
        return execute_agent_run(params)

    if method == "get_window":
        hwnd = _window_id_from_params(params)
        window = get_window(hwnd)
        return {"ok": True, "window": window.to_dict()}

    if method == "activate_window":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "activate_window", activate=True)
        return {"ok": True, "action": "activate_window", "window": window.to_dict()}

    if method == "get_window_state":
        return build_window_state(params, default_screenshot=True)

    if method == "observe":
        return observe_window(params)

    if method == "wait":
        seconds = float(params.get("seconds", 0.0))
        if params.get("timeout_ms") is not None:
            seconds = float(params["timeout_ms"]) / 1000.0
        elif params.get("timeout") is not None:
            seconds = float(params["timeout"])
        seconds = max(0.0, min(seconds, 60.0))
        if seconds:
            time.sleep(seconds)
        return {"ok": True, "action": "wait", "seconds": seconds}

    if method == "list_windows":
        windows = list_windows(
            include_hidden=bool(params.get("include_hidden", False)),
            query=params.get("query"),
        )
        return {
            "ok": True,
            "version": __version__,
            "windows": [window.to_dict() for window in windows],
        }

    if method == "list_apps":
        include_windows = bool(params.get("include_windows", True))
        apps = list_apps(
            query=params.get("query"),
            include_windows=include_windows,
            include_start_menu=bool(params.get("include_start_menu", True)),
            include_running=bool(params.get("include_running", True)),
            limit=int(params["limit"]) if params.get("limit") is not None else None,
        )
        return {
            "ok": True,
            "version": __version__,
            "apps": [app.to_dict(include_windows=include_windows) for app in apps],
        }

    if method == "launch_app":
        app_args = params.get("args", [])
        if not isinstance(app_args, list):
            raise DesktopControlError("invalid_request", "launch_app args must be a list")
        return launch_app(
            str(_require(params, "app")),
            args=[str(item) for item in app_args],
            cwd=str(params["cwd"]) if params.get("cwd") is not None else None,
            wait=bool(params.get("wait", True)),
            wait_query=str(params["wait_query"]) if params.get("wait_query") is not None else None,
            timeout_seconds=float(params.get("timeout", 10.0)),
            interval_seconds=float(params.get("interval", 0.1)),
        )

    if method == "state":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "state", activate=bool(params.get("activate", False)))
        result: dict[str, Any] = {"ok": True, "window": window.to_dict()}
        if params.get("screenshot"):
            result["screenshot"] = capture_window(
                hwnd,
                str(params["screenshot"]),
                backend=params.get("screenshot_backend", "auto"),
            )
        if params.get("include_ui", False):
            result["ui"] = get_uia_tree(
                hwnd,
                max_depth=int(params.get("max_depth", 3)),
                max_nodes=int(params.get("max_nodes", 200)),
            )
        return result

    if method == "screenshot":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "screenshot", activate=bool(params.get("activate", False)))
        screenshot = _screenshot_payload(hwnd, params)
        return {
            "ok": True,
            "window": window.to_dict(),
            "screenshot": screenshot,
        }

    if method == "click":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "click", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        click_at(
            x,
            y,
            button=params.get("button", params.get("mouse_button", "left")),
            count=int(params.get("count", params.get("click_count", 1))),
        )
        return {"ok": True, "action": "click", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "move":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "move", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        move_to(x, y)
        return {"ok": True, "action": "move", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "scroll":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "scroll", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        raw_delta = params.get("delta")
        if raw_delta is None:
            scroll_y = params.get("scrollY", params.get("scroll_y"))
            if scroll_y is None:
                raise DesktopControlError("invalid_request", "Missing required parameter: delta")
            raw_scroll_y = float(scroll_y)
            raw_delta = -round(raw_scroll_y / 120.0)
            if raw_delta == 0 and raw_scroll_y != 0:
                raw_delta = -1 if raw_scroll_y > 0 else 1
        scroll_at(x, y, int(raw_delta))
        return {"ok": True, "action": "scroll", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "drag":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "drag", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        from_x, from_y = _resolve_checked_point(
            hwnd,
            int(_require(params, "from_x")),
            int(_require(params, "from_y")),
            params.get("space", "window"),
        )
        to_x, to_y = _resolve_checked_point(
            hwnd,
            int(_require(params, "to_x")),
            int(_require(params, "to_y")),
            params.get("space", "window"),
        )
        drag_at(
            from_x,
            from_y,
            to_x,
            to_y,
            button=params.get("button", "left"),
            duration_seconds=float(params.get("duration", 0.2)),
            steps=int(params.get("steps", 12)),
        )
        return {"ok": True, "action": "drag", "window": window.to_dict(), "from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}

    if method == "type_text":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "type_text", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        text = str(params.get("text", ""))
        if params.get("text_file"):
            text = Path(str(params["text_file"])).read_text(encoding="utf-8")
        text_method = str(params.get("method", "clipboard"))
        send_text(text, method=text_method)
        return {"ok": True, "action": "type_text", "window": window.to_dict(), "characters": len(text), "method": text_method}

    if method == "key":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "key", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        keys = params.get("keys")
        if keys is None and "key" in params:
            keys = [params["key"]]
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, list) or not keys:
            raise DesktopControlError("invalid_request", "keys must be a non-empty list")
        press_key_sequence([str(key) for key in keys])
        return {"ok": True, "action": "key", "window": window.to_dict(), "keys": keys}

    if method == "find_elements":
        hwnd = _window_id_from_params(params)
        selector = _selector_from_params(params)
        window = _window_for_action(hwnd, "find_elements", activate=False)
        return {
            "ok": True,
            "window": window.to_dict(),
            "selector": selector,
            "elements": find_uia_elements(
                hwnd,
                selector,
                max_depth=int(params.get("max_depth", 6)),
                max_nodes=int(params.get("max_nodes", 500)),
            ),
        }

    if method == "click_element":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "click_element", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        result = click_uia_element(
            hwnd,
            _selector_from_params(params),
            button=str(params.get("button", "left")),
            count=int(params.get("count", 1)),
            max_depth=int(params.get("max_depth", 6)),
            max_nodes=int(params.get("max_nodes", 500)),
        )
        result["window"] = window.to_dict()
        return result

    if method == "invoke_element":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "invoke_element", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        result = invoke_uia_element(
            hwnd,
            _selector_from_params(params),
            max_depth=int(params.get("max_depth", 6)),
            max_nodes=int(params.get("max_nodes", 500)),
        )
        result["window"] = window.to_dict()
        return result

    if method == "set_element_value":
        hwnd = _window_id_from_params(params)
        window = _window_for_action(hwnd, "set_element_value", activate=bool(params.get("activate", True)))
        _enforce_expected_snapshot(window, params)
        value = str(params.get("value", ""))
        if params.get("value_file"):
            value = Path(str(params["value_file"])).read_text(encoding="utf-8")
        result = set_uia_element_value(
            hwnd,
            _selector_from_params(params),
            value,
            max_depth=int(params.get("max_depth", 6)),
            max_nodes=int(params.get("max_nodes", 500)),
            fallback_text_method=str(params.get("fallback_text_method", "clipboard")),
        )
        result["window"] = window.to_dict()
        return result

    if method == "wait_window":
        return wait_for_window(
            query=params.get("query"),
            timeout_seconds=float(params.get("timeout", 10.0)),
            interval_seconds=float(params.get("interval", 0.1)),
            include_hidden=bool(params.get("include_hidden", False)),
        )

    if method == "wait_element":
        hwnd = _window_id_from_params(params)
        selector = _selector_from_params(params)
        window = _window_for_action(hwnd, "wait_element", activate=False)
        result = wait_for_element(
            hwnd,
            selector,
            timeout_seconds=float(params.get("timeout", 10.0)),
            interval_seconds=float(params.get("interval", 0.1)),
            max_depth=int(params.get("max_depth", 6)),
            max_nodes=int(params.get("max_nodes", 500)),
        )
        result["window"] = window.to_dict()
        return result

    if method == "recover_window":
        ref = _window_ref_from_params(params)
        window = resolve_window_ref(
            ref,
            include_hidden=bool(params.get("include_hidden", False)),
            allow_ambiguous=bool(params.get("allow_ambiguous", False)),
        )
        return {
            "ok": True,
            "action": "recover_window",
            "input_ref": ref,
            "window": window.to_dict(),
        }

    raise DesktopControlError("method_not_found", f"Unknown method: {method}")


def _window_ref_from_params(params: dict[str, Any]) -> dict[str, Any]:
    raw_ref = params.get("window_ref")
    if isinstance(raw_ref, dict):
        return dict(raw_ref)
    ref: dict[str, Any] = {}
    for param_name, ref_name in (
        ("window_id", "hwnd"),
        ("hwnd", "hwnd"),
        ("process_id", "process_id"),
        ("process_name", "process_name"),
        ("title", "title"),
        ("title_contains", "title_contains"),
        ("class_name", "class_name"),
    ):
        value = params.get(param_name)
        if value not in (None, ""):
            ref[ref_name] = value
    if not ref:
        raise DesktopControlError(
            "invalid_window_ref",
            "recover_window requires window_ref or at least one identity field",
        )
    return ref


def handle_rpc_request(request: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _rpc_error(None, -32600, "Invalid Request")
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(method, str):
        return _rpc_error(request_id, -32600, "Invalid Request", {"reason": "method must be a string"})
    if not isinstance(params, dict):
        return _rpc_error(request_id, -32602, "Invalid params", {"reason": "params must be an object"})

    try:
        result = _handle_method(method, params)
        record_audit_event("rpc", method, params, result=result)
        if request_id is None:
            return None
        return _rpc_success(request_id, result)
    except DesktopControlError as exc:
        record_audit_event(
            "rpc",
            method,
            params,
            error={"code": exc.code, "message": exc.message, "details": exc.details},
        )
        return _rpc_error(
            request_id,
            -32000,
            exc.message,
            {"desktop_code": exc.code, "details": exc.details},
        )


def handle_rpc_payload(payload: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(payload, list):
        if not payload:
            return _rpc_error(None, -32600, "Invalid Request", {"reason": "batch cannot be empty"})
        responses = [response for response in (handle_rpc_request(item) for item in payload) if response is not None]
        return responses or None
    return handle_rpc_request(payload)


def serve_stdio() -> int:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            request = json.loads(stripped)
        except json.JSONDecodeError as exc:
            response = _rpc_error(None, -32700, "Parse error", {"details": str(exc)})
        else:
            response = handle_rpc_payload(request)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0
