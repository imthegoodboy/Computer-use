from desktop_control.rpc import handle_rpc_request


def test_rpc_rejects_unknown_method():
    response = handle_rpc_request({"jsonrpc": "2.0", "id": 1, "method": "missing", "params": {}})
    assert response is not None
    assert response["id"] == 1
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["desktop_code"] == "method_not_found"


def test_rpc_rejects_non_object_params():
    response = handle_rpc_request({"jsonrpc": "2.0", "id": 2, "method": "list_windows", "params": []})
    assert response is not None
    assert response["id"] == 2
    assert response["error"]["code"] == -32602


def test_rpc_rejects_missing_uia_selector():
    response = handle_rpc_request({"jsonrpc": "2.0", "id": 3, "method": "find_elements", "params": {"window_id": 1}})
    assert response is not None
    assert response["id"] == 3
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["desktop_code"] == "invalid_selector"


def test_rpc_rejects_missing_wait_element_selector():
    response = handle_rpc_request({"jsonrpc": "2.0", "id": 4, "method": "wait_element", "params": {"window_id": 1}})
    assert response is not None
    assert response["id"] == 4
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["desktop_code"] == "invalid_selector"


def test_rpc_rejects_stale_snapshot_before_keypress(monkeypatch):
    from desktop_control import rpc
    from desktop_control.models import Rect, WindowInfo

    target = WindowInfo(
        hwnd=1,
        title="Target",
        process_id=10,
        process_name="target.exe",
        class_name="TargetWindow",
        rect=Rect(0, 0, 200, 100),
        visible=True,
        minimized=False,
        client_rect=Rect(0, 0, 200, 100),
    )
    monkeypatch.setattr(rpc, "_window_for_action", lambda hwnd, action, activate=True: target)

    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "key",
            "params": {"window_id": 1, "keys": ["enter"], "expect_snapshot_id": "bad"},
        }
    )
    assert response is not None
    assert response["id"] == 5
    assert response["error"]["data"]["desktop_code"] == "stale_snapshot"
