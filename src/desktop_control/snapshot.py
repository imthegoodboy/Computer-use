from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import DesktopControlError


def stable_snapshot_id(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]


def assert_expected_snapshot(current_snapshot_id: str, expected_snapshot_id: str | None) -> None:
    if not expected_snapshot_id:
        return
    if current_snapshot_id != expected_snapshot_id:
        raise DesktopControlError(
            "stale_snapshot",
            "Window state no longer matches the expected snapshot",
            {
                "expected_snapshot_id": expected_snapshot_id,
                "current_snapshot_id": current_snapshot_id,
            },
        )
