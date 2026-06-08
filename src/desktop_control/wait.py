from __future__ import annotations

import time
from typing import Any

from .errors import DesktopControlError
from .uia import find_uia_elements
from .windows import list_windows


def _deadline(timeout_seconds: float) -> float:
    return time.monotonic() + max(0.0, timeout_seconds)


def wait_for_window(
    query: str | None = None,
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.1,
    include_hidden: bool = False,
) -> dict[str, Any]:
    deadline = _deadline(timeout_seconds)
    attempts = 0
    last_count = 0

    while True:
        attempts += 1
        matches = list_windows(include_hidden=include_hidden, query=query)
        last_count = len(matches)
        if matches:
            return {
                "ok": True,
                "action": "wait_window",
                "attempts": attempts,
                "window": matches[0].to_dict(),
                "matches": [window.to_dict() for window in matches],
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.01, interval_seconds))

    raise DesktopControlError(
        "wait_timeout",
        "Timed out waiting for a matching window",
        {
            "query": query,
            "timeout_seconds": timeout_seconds,
            "attempts": attempts,
            "last_count": last_count,
        },
    )


def wait_for_element(
    hwnd: int,
    selector: dict[str, Any],
    timeout_seconds: float = 10.0,
    interval_seconds: float = 0.1,
    max_depth: int = 6,
    max_nodes: int = 500,
) -> dict[str, Any]:
    deadline = _deadline(timeout_seconds)
    attempts = 0
    last_count = 0

    while True:
        attempts += 1
        matches = find_uia_elements(hwnd, selector, max_depth=max_depth, max_nodes=max_nodes)
        last_count = len(matches)
        if matches:
            return {
                "ok": True,
                "action": "wait_element",
                "attempts": attempts,
                "selector": selector,
                "element": matches[0],
                "matches": matches,
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.01, interval_seconds))

    raise DesktopControlError(
        "wait_timeout",
        "Timed out waiting for a matching UIA element",
        {
            "hwnd": hwnd,
            "selector": selector,
            "timeout_seconds": timeout_seconds,
            "attempts": attempts,
            "last_count": last_count,
        },
    )
