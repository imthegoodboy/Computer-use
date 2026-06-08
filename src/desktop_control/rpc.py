from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .audit import record_audit_event
from .capture import capture_window
from .cli import _resolve_checked_point, _window_for_action
from .errors import DesktopControlError
from .input import click_at, drag_at, move_to, press_key_sequence, scroll_at, send_text
from .uia import click_uia_element, find_uia_elements, get_uia_tree, invoke_uia_element, set_uia_element_value
from .wait import wait_for_element, wait_for_window
from .windows import list_windows


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


def _handle_method(method: str, params: dict[str, Any]) -> dict[str, Any]:
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

    if method == "state":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "state", activate=bool(params.get("activate", False)))
        result: dict[str, Any] = {"ok": True, "window": window.to_dict()}
        if params.get("screenshot"):
            result["screenshot"] = capture_window(hwnd, str(params["screenshot"]))
        if params.get("include_ui", False):
            result["ui"] = get_uia_tree(
                hwnd,
                max_depth=int(params.get("max_depth", 3)),
                max_nodes=int(params.get("max_nodes", 200)),
            )
        return result

    if method == "screenshot":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "screenshot", activate=bool(params.get("activate", False)))
        return {
            "ok": True,
            "window": window.to_dict(),
            "screenshot": capture_window(hwnd, str(_require(params, "out"))),
        }

    if method == "click":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "click", activate=bool(params.get("activate", True)))
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        click_at(x, y, button=params.get("button", "left"), count=int(params.get("count", 1)))
        return {"ok": True, "action": "click", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "move":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "move", activate=bool(params.get("activate", True)))
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        move_to(x, y)
        return {"ok": True, "action": "move", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "scroll":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "scroll", activate=bool(params.get("activate", True)))
        x, y = _resolve_checked_point(
            hwnd,
            int(_require(params, "x")),
            int(_require(params, "y")),
            params.get("space", "window"),
        )
        scroll_at(x, y, int(_require(params, "delta")))
        return {"ok": True, "action": "scroll", "window": window.to_dict(), "screen_point": {"x": x, "y": y}}

    if method == "drag":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "drag", activate=bool(params.get("activate", True)))
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
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "type_text", activate=bool(params.get("activate", True)))
        text = str(params.get("text", ""))
        if params.get("text_file"):
            text = Path(str(params["text_file"])).read_text(encoding="utf-8")
        text_method = str(params.get("method", "clipboard"))
        send_text(text, method=text_method)
        return {"ok": True, "action": "type_text", "window": window.to_dict(), "characters": len(text), "method": text_method}

    if method == "key":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "key", activate=bool(params.get("activate", True)))
        keys = params.get("keys")
        if not isinstance(keys, list) or not keys:
            raise DesktopControlError("invalid_request", "keys must be a non-empty list")
        press_key_sequence([str(key) for key in keys])
        return {"ok": True, "action": "key", "window": window.to_dict(), "keys": keys}

    if method == "find_elements":
        hwnd = int(_require(params, "window_id"))
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
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "click_element", activate=bool(params.get("activate", True)))
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
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "invoke_element", activate=bool(params.get("activate", True)))
        result = invoke_uia_element(
            hwnd,
            _selector_from_params(params),
            max_depth=int(params.get("max_depth", 6)),
            max_nodes=int(params.get("max_nodes", 500)),
        )
        result["window"] = window.to_dict()
        return result

    if method == "set_element_value":
        hwnd = int(_require(params, "window_id"))
        window = _window_for_action(hwnd, "set_element_value", activate=bool(params.get("activate", True)))
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
        hwnd = int(_require(params, "window_id"))
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

    raise DesktopControlError("method_not_found", f"Unknown method: {method}")


def _selector_from_params(params: dict[str, Any]) -> dict[str, Any]:
    raw_selector = params.get("selector")
    if isinstance(raw_selector, dict):
        selector = dict(raw_selector)
    else:
        selector = {}
        for key in ("name", "name_contains", "automation_id", "class_name", "control_type", "index", "allow_multiple"):
            if key in params:
                selector[key] = params[key]
    if not selector:
        raise DesktopControlError("invalid_selector", "At least one UIA selector field is required")
    return selector


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
            response = handle_rpc_request(request)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0
