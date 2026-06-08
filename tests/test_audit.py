import json

from desktop_control.audit import AUDIT_LOG_ENV, record_audit_event


def test_audit_log_redacts_sensitive_fields(monkeypatch, tmp_path):
    log_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv(AUDIT_LOG_ENV, str(log_path))

    record_audit_event(
        "test",
        "type_text",
        {"text": "hello", "window_id": 123},
        result={"ok": True, "value": "secret-value"},
    )

    event = json.loads(log_path.read_text(encoding="utf-8"))
    assert event["source"] == "test"
    assert event["action"] == "type_text"
    assert event["status"] == "success"
    assert event["params"]["text"] == {"redacted": True, "length": 5}
    assert event["params"]["window_id"] == 123
    assert event["result"]["value"] == {"redacted": True, "length": 12}


def test_audit_log_is_disabled_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv(AUDIT_LOG_ENV, raising=False)
    record_audit_event("test", "click", {"x": 1}, result={"ok": True})
    assert list(tmp_path.iterdir()) == []
