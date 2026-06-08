from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

AUDIT_LOG_ENV = "DESKTOP_CONTROL_AUDIT_LOG"
SENSITIVE_KEYS = {"arg", "args", "password", "secret", "text", "token", "value"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in SENSITIVE_KEYS:
                sanitized[key] = {
                    "redacted": True,
                    "length": len(str(item)) if item is not None else 0,
                }
            else:
                sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def audit_log_path() -> Path | None:
    configured = os.environ.get(AUDIT_LOG_ENV)
    if not configured:
        return None
    return Path(configured)


def record_audit_event(
    source: str,
    action: str | None,
    params: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    path = audit_log_path()
    if path is None:
        return

    payload = {
        "time": time.time(),
        "source": source,
        "action": action,
        "status": "error" if error else "success",
        "params": _sanitize(params or {}),
    }
    if result is not None:
        payload["result"] = _sanitize(result)
    if error is not None:
        payload["error"] = _sanitize(error)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
