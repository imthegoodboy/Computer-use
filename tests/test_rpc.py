from desktop_control.rpc import handle_rpc_payload, handle_rpc_request


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


def test_rpc_batch_runs_multiple_safe_actions():
    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "batch",
            "params": {
                "actions": [
                    {"method": "list_windows", "params": {"query": "unlikely-test-window"}},
                    {"method": "list_windows", "params": {"query": "another-unlikely-test-window"}},
                ]
            },
        }
    )
    assert response is not None
    assert response["result"]["ok"] is True
    assert response["result"]["count"] == 2


def test_rpc_lists_apps(monkeypatch):
    from desktop_control import rpc
    from desktop_control.apps import AppInfo

    monkeypatch.setattr(
        rpc,
        "list_apps",
        lambda query=None, include_windows=True, include_start_menu=True, include_running=True, limit=None: [
            AppInfo(id="app-1", display_name="App One", source="running", process_name="app.exe", running=True)
        ],
    )

    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "list_apps",
            "params": {"query": "app", "include_windows": False},
        }
    )

    assert response is not None
    assert response["result"]["apps"][0]["id"] == "app-1"


def test_rpc_launches_app(monkeypatch):
    from desktop_control import rpc

    captured = {}

    def fake_launch_app(app, args=None, cwd=None, wait=True, wait_query=None, timeout_seconds=10.0, interval_seconds=0.1):
        captured.update(
            {
                "app": app,
                "args": args,
                "cwd": cwd,
                "wait": wait,
                "wait_query": wait_query,
                "timeout_seconds": timeout_seconds,
                "interval_seconds": interval_seconds,
            }
        )
        return {"ok": True, "action": "launch_app"}

    monkeypatch.setattr(rpc, "launch_app", fake_launch_app)

    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "launch_app",
            "params": {"app": "notepad.exe", "args": ["a.txt"], "wait": False},
        }
    )

    assert response is not None
    assert response["result"]["ok"] is True
    assert captured["app"] == "notepad.exe"
    assert captured["args"] == ["a.txt"]
    assert captured["wait"] is False


def test_rpc_launch_app_rejects_non_list_args():
    response = handle_rpc_request(
        {"jsonrpc": "2.0", "id": 9, "method": "launch_app", "params": {"app": "notepad.exe", "args": "bad"}}
    )
    assert response is not None
    assert response["error"]["data"]["desktop_code"] == "invalid_request"


def test_rpc_batch_rejects_nested_batch():
    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "batch",
            "params": {"actions": [{"method": "batch", "params": {"actions": []}}]},
        }
    )
    assert response is not None
    assert response["error"]["data"]["desktop_code"] == "batch_action_failed"
    assert response["error"]["data"]["details"]["results"][0]["error"]["code"] == "invalid_request"


def test_rpc_recovers_window_ref(monkeypatch):
    from desktop_control import rpc
    from desktop_control.models import Rect, WindowInfo

    target = WindowInfo(
        hwnd=44,
        title="Recovered",
        process_id=12,
        process_name="target.exe",
        class_name="TargetWindow",
        rect=Rect(0, 0, 200, 100),
        visible=True,
        minimized=False,
        client_rect=Rect(0, 0, 200, 100),
    )
    captured = {}

    def fake_resolve(ref, include_hidden=False, allow_ambiguous=False):
        captured["ref"] = ref
        captured["include_hidden"] = include_hidden
        captured["allow_ambiguous"] = allow_ambiguous
        return target

    monkeypatch.setattr(rpc, "resolve_window_ref", fake_resolve)

    response = handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "recover_window",
            "params": {
                "window_ref": {"process_name": "target.exe", "title": "Recovered"},
                "include_hidden": True,
            },
        }
    )

    assert response is not None
    assert response["result"]["window"]["hwnd"] == 44
    assert captured == {
        "ref": {"process_name": "target.exe", "title": "Recovered"},
        "include_hidden": True,
        "allow_ambiguous": False,
    }


def test_rpc_recover_window_requires_identity():
    response = handle_rpc_request({"jsonrpc": "2.0", "id": 12, "method": "recover_window", "params": {}})
    assert response is not None
    assert response["error"]["data"]["desktop_code"] == "invalid_window_ref"


def test_json_rpc_batch_payload_returns_multiple_responses():
    response = handle_rpc_payload(
        [
            {"jsonrpc": "2.0", "id": 13, "method": "list_windows", "params": {"query": "a"}},
            {"jsonrpc": "2.0", "id": 14, "method": "list_windows", "params": {"query": "b"}},
        ]
    )
    assert isinstance(response, list)
    assert [item["id"] for item in response] == [13, 14]
