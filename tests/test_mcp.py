from desktop_control.errors import DesktopControlError
from desktop_control.mcp import MCP_TO_RPC_METHOD, handle_mcp_payload, handle_mcp_request


def test_mcp_initialize_declares_tools_capability():
    response = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "0"},
            },
        }
    )

    assert response is not None
    assert response["id"] == 1
    assert response["result"]["protocolVersion"] == "2025-06-18"
    assert response["result"]["capabilities"]["tools"]["listChanged"] is False
    assert response["result"]["serverInfo"]["name"] == "desktop-control"


def test_mcp_tools_list_exposes_desktop_tools():
    response = handle_mcp_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    assert response is not None
    tools = response["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "list_windows" in names
    assert "get_window_state" in names
    assert "press_key" in names
    assert "batch" in names
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)


def test_mcp_tools_list_covers_registered_tool_mapping():
    response = handle_mcp_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})

    assert response is not None
    listed = {tool["name"] for tool in response["result"]["tools"]}
    assert listed == set(MCP_TO_RPC_METHOD)


def test_mcp_tools_call_returns_structured_content(monkeypatch):
    from desktop_control import mcp

    captured = {}

    def fake_handle(method, params):
        captured["method"] = method
        captured["params"] = params
        return {"ok": True, "windows": []}

    monkeypatch.setattr(mcp, "_handle_method", fake_handle)

    response = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_windows", "arguments": {"query": "none"}},
        }
    )

    assert response is not None
    result = response["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == {"ok": True, "windows": []}
    assert result["content"][0]["type"] == "text"
    assert captured == {"method": "list_windows", "params": {"query": "none"}}


def test_mcp_tool_execution_errors_are_tool_results(monkeypatch):
    from desktop_control import mcp

    def fake_handle(method, params):
        raise DesktopControlError("approval_required", "Target needs approval", {"window_id": 1})

    monkeypatch.setattr(mcp, "_handle_method", fake_handle)

    response = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "click", "arguments": {"window_id": 1, "x": 10, "y": 20}},
        }
    )

    assert response is not None
    result = response["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "approval_required"


def test_mcp_unknown_tool_is_protocol_error():
    response = handle_mcp_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "missing_tool", "arguments": {}},
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["tool"] == "missing_tool"


def test_mcp_notification_has_no_response():
    assert handle_mcp_request({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) is None


def test_mcp_batch_payload_omits_notification_response():
    response = handle_mcp_payload(
        [
            {"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        ]
    )

    assert isinstance(response, list)
    assert len(response) == 1
    assert response[0]["id"] == 7
