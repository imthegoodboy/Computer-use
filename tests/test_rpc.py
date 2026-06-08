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
