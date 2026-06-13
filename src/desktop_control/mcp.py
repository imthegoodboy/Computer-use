from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .audit import record_audit_event
from .errors import DesktopControlError
from .rpc import _handle_method

LATEST_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
}


def _object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        schema["required"] = required
    if description:
        schema["description"] = description
    return schema


WINDOW_TARGET_PROPERTIES = {
    "window_id": {"type": "integer", "description": "Target window HWND/id."},
    "window": {
        "type": "object",
        "description": "Codex-style window object containing id/hwnd and optional app.",
        "properties": {
            "id": {"type": "integer"},
            "hwnd": {"type": "integer"},
            "app": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "activate": {"type": "boolean", "description": "Bring the window foreground before action."},
    "expect_snapshot_id": {
        "type": "string",
        "description": "Reject the action if the current window snapshot id differs.",
    },
}

COORDINATE_PROPERTIES = {
    **WINDOW_TARGET_PROPERTIES,
    "x": {"type": "integer"},
    "y": {"type": "integer"},
    "space": {"type": "string", "enum": ["window", "client", "screen"]},
}

UIA_SELECTOR_PROPERTIES = {
    **WINDOW_TARGET_PROPERTIES,
    "name": {"type": "string"},
    "name_contains": {"type": "string"},
    "automation_id": {"type": "string"},
    "class_name": {"type": "string"},
    "control_type": {"type": "string"},
    "element_index": {"type": "integer"},
    "index": {"type": "integer"},
    "allow_multiple": {"type": "boolean"},
    "max_depth": {"type": "integer"},
    "max_nodes": {"type": "integer"},
}


MCP_TO_RPC_METHOD = {
    "list_apps": "list_apps",
    "list_windows": "list_windows",
    "launch_app": "launch_app",
    "get_window": "get_window",
    "activate_window": "activate_window",
    "get_window_state": "get_window_state",
    "screenshot": "screenshot",
    "click": "click",
    "double_click": "double_click",
    "move": "move",
    "scroll": "scroll",
    "drag": "drag",
    "type_text": "type_text",
    "press_key": "press_key",
    "find_elements": "find_elements",
    "click_element": "click_element",
    "invoke_element": "invoke_element",
    "set_value": "set_value",
    "wait": "wait",
    "wait_window": "wait_window",
    "wait_element": "wait_element",
    "recover_window": "recover_window",
    "batch": "batch",
}


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_apps",
        "title": "List Desktop Apps",
        "description": "List launchable and running desktop apps, including open targetable windows by default.",
        "inputSchema": _object_schema(
            {
                "query": {"type": "string"},
                "include_windows": {"type": "boolean"},
                "include_start_menu": {"type": "boolean"},
                "include_running": {"type": "boolean"},
                "limit": {"type": "integer"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "list_windows",
        "title": "List Desktop Windows",
        "description": "List visible top-level windows. Start here before selecting a target.",
        "inputSchema": _object_schema({"query": {"type": "string"}, "include_hidden": {"type": "boolean"}}),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "launch_app",
        "title": "Launch App",
        "description": "Launch an app by id, display name, process name, shortcut, or executable path, then optionally wait for a matching window.",
        "inputSchema": _object_schema(
            {
                "app": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string"},
                "wait": {"type": "boolean"},
                "wait_query": {"type": "string"},
                "timeout": {"type": "number"},
                "interval": {"type": "number"},
            },
            required=["app"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "get_window",
        "title": "Get Window",
        "description": "Rehydrate a current target window by id/hwnd.",
        "inputSchema": _object_schema(WINDOW_TARGET_PROPERTIES),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "activate_window",
        "title": "Activate Window",
        "description": "Restore and activate the target window.",
        "inputSchema": _object_schema(WINDOW_TARGET_PROPERTIES),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_window_state",
        "title": "Get Visual Window State",
        "description": "Capture an agent-facing window snapshot. Screenshot is included by default; include_text adds UI Automation metadata.",
        "inputSchema": _object_schema(
            {
                **WINDOW_TARGET_PROPERTIES,
                "include_screenshot": {"type": "boolean"},
                "include_text": {"type": "boolean"},
                "out": {"type": "string", "description": "Optional screenshot output path."},
                "screenshot_backend": {"type": "string", "enum": ["auto", "pil", "mss"]},
                "max_depth": {"type": "integer"},
                "max_nodes": {"type": "integer"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "screenshot",
        "title": "Capture Screenshot",
        "description": "Capture a screenshot for a target window.",
        "inputSchema": _object_schema(
            {
                **WINDOW_TARGET_PROPERTIES,
                "out": {"type": "string"},
                "backend": {"type": "string", "enum": ["auto", "pil", "mss"]},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "click",
        "title": "Click",
        "description": "Click a window-relative, client-relative, or screen coordinate.",
        "inputSchema": _object_schema(
            {
                **COORDINATE_PROPERTIES,
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "mouse_button": {"type": "string", "enum": ["left", "right", "middle"]},
                "count": {"type": "integer"},
                "click_count": {"type": "integer"},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "double_click",
        "title": "Double Click",
        "description": "Double-click a coordinate in the target window.",
        "inputSchema": _object_schema(COORDINATE_PROPERTIES),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "move",
        "title": "Move Cursor",
        "description": "Move the mouse cursor to a target coordinate.",
        "inputSchema": _object_schema(COORDINATE_PROPERTIES),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "scroll",
        "title": "Scroll",
        "description": "Scroll at a coordinate. Use delta wheel ticks or OpenAI-style scrollY.",
        "inputSchema": _object_schema(
            {
                **COORDINATE_PROPERTIES,
                "delta": {"type": "integer"},
                "scrollY": {"type": "number"},
                "scrollX": {"type": "number"},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True},
    },
    {
        "name": "drag",
        "title": "Drag",
        "description": "Drag from one coordinate to another inside the target window.",
        "inputSchema": _object_schema(
            {
                **WINDOW_TARGET_PROPERTIES,
                "from_x": {"type": "integer"},
                "from_y": {"type": "integer"},
                "to_x": {"type": "integer"},
                "to_y": {"type": "integer"},
                "space": {"type": "string", "enum": ["window", "client", "screen"]},
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "duration": {"type": "number"},
                "steps": {"type": "integer"},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "type_text",
        "title": "Type Text",
        "description": "Type text into the focused control in a target window.",
        "inputSchema": _object_schema(
            {
                **WINDOW_TARGET_PROPERTIES,
                "text": {"type": "string"},
                "text_file": {"type": "string"},
                "method": {"type": "string", "enum": ["clipboard", "unicode"]},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "press_key",
        "title": "Press Key",
        "description": "Press one key chord or a sequence of key chords in a target window.",
        "inputSchema": _object_schema(
            {
                **WINDOW_TARGET_PROPERTIES,
                "key": {"type": "string"},
                "keys": {"type": "array", "items": {"type": "string"}},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "find_elements",
        "title": "Find UI Elements",
        "description": "Find Windows UI Automation elements by selector.",
        "inputSchema": _object_schema(UIA_SELECTOR_PROPERTIES),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "click_element",
        "title": "Click UI Element",
        "description": "Click a matching UI Automation element.",
        "inputSchema": _object_schema(
            {
                **UIA_SELECTOR_PROPERTIES,
                "button": {"type": "string", "enum": ["left", "right", "middle"]},
                "count": {"type": "integer"},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "invoke_element",
        "title": "Invoke UI Element",
        "description": "Invoke a matching UI Automation element, falling back to a center click if needed.",
        "inputSchema": _object_schema(UIA_SELECTOR_PROPERTIES),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "set_value",
        "title": "Set UI Element Value",
        "description": "Set a matching editable UI Automation element value.",
        "inputSchema": _object_schema(
            {
                **UIA_SELECTOR_PROPERTIES,
                "value": {"type": "string"},
                "value_file": {"type": "string"},
                "fallback_text_method": {"type": "string", "enum": ["clipboard", "unicode"]},
            }
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "wait",
        "title": "Wait",
        "description": "Wait for a short duration without a blind action.",
        "inputSchema": _object_schema(
            {
                "seconds": {"type": "number"},
                "timeout": {"type": "number"},
                "timeout_ms": {"type": "number"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "wait_window",
        "title": "Wait For Window",
        "description": "Wait until a matching top-level window appears.",
        "inputSchema": _object_schema(
            {
                "query": {"type": "string"},
                "timeout": {"type": "number"},
                "interval": {"type": "number"},
                "include_hidden": {"type": "boolean"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "wait_element",
        "title": "Wait For UI Element",
        "description": "Wait until a matching UI Automation element appears in a target window.",
        "inputSchema": _object_schema(
            {
                **UIA_SELECTOR_PROPERTIES,
                "timeout": {"type": "number"},
                "interval": {"type": "number"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "recover_window",
        "title": "Recover Window",
        "description": "Recover a current window from a saved window_ref or identity fields.",
        "inputSchema": _object_schema(
            {
                "window_ref": {"type": "object", "additionalProperties": True},
                "window_id": {"type": "integer"},
                "hwnd": {"type": "integer"},
                "process_id": {"type": "integer"},
                "process_name": {"type": "string"},
                "title": {"type": "string"},
                "title_contains": {"type": "string"},
                "class_name": {"type": "string"},
                "include_hidden": {"type": "boolean"},
                "allow_ambiguous": {"type": "boolean"},
            }
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "batch",
        "title": "Batch Desktop Actions",
        "description": "Run multiple stable desktop-control actions before one verification snapshot.",
        "inputSchema": _object_schema(
            {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "method": {"type": "string"},
                            "params": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["method"],
                        "additionalProperties": True,
                    },
                },
                "stop_on_error": {"type": "boolean"},
            },
            required=["actions"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
]


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _selected_protocol_version(params: dict[str, Any]) -> str:
    requested = params.get("protocolVersion")
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name not in MCP_TO_RPC_METHOD:
        raise DesktopControlError("tool_not_found", f"Unknown MCP tool: {name}", {"tool": name})
    args = arguments or {}
    if not isinstance(args, dict):
        raise DesktopControlError("invalid_request", "MCP tool arguments must be an object", {"tool": name})
    method = MCP_TO_RPC_METHOD[name]
    try:
        result = _handle_method(method, args)
        record_audit_event("mcp", name, args, result=result)
        return _tool_result(result)
    except DesktopControlError as exc:
        error_payload = exc.to_dict()
        record_audit_event("mcp", name, args, error=error_payload["error"])
        return _tool_result(error_payload, is_error=True)


def handle_mcp_request(request: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _error(None, -32600, "Invalid Request")
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(method, str):
        return _error(request_id, -32600, "Invalid Request", {"reason": "method must be a string"})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(request_id, -32602, "Invalid params", {"reason": "params must be an object"})

    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _success(request_id, {})
    if method == "initialize":
        result = {
            "protocolVersion": _selected_protocol_version(params),
            "serverInfo": {"name": "desktop-control", "version": __version__},
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": (
                "Use list_apps or list_windows first, select exactly one target window, "
                "call get_window_state for visual grounding, batch stable actions, then verify. "
                "The server enforces desktop-control safety policy and may deny sensitive targets."
            ),
        }
        return _success(request_id, result)
    if method == "tools/list":
        return _success(request_id, {"tools": MCP_TOOLS})
    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            return _error(request_id, -32602, "Invalid params", {"reason": "tool name must be a string"})
        if tool_name not in MCP_TO_RPC_METHOD:
            return _error(request_id, -32602, "Unknown tool", {"tool": tool_name})
        arguments = params.get("arguments", {})
        try:
            return _success(request_id, call_tool(tool_name, arguments))
        except DesktopControlError as exc:
            return _error(request_id, -32602, exc.message, {"desktop_code": exc.code, "details": exc.details})

    return _error(request_id, -32601, f"Method not found: {method}")


def handle_mcp_payload(payload: Any) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(payload, list):
        if not payload:
            return _error(None, -32600, "Invalid Request", {"reason": "batch cannot be empty"})
        responses = [response for response in (handle_mcp_request(item) for item in payload) if response is not None]
        return responses or None
    return handle_mcp_request(payload)


def serve_mcp_stdio() -> int:
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            request = json.loads(stripped)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, "Parse error", {"details": str(exc)})
        else:
            response = handle_mcp_payload(request)
        if response is not None:
            print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0
