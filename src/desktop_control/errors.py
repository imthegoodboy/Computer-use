from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DesktopControlError(RuntimeError):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def wrap_os_error(code: str, message: str, exc: BaseException) -> DesktopControlError:
    return DesktopControlError(code, message, {"exception": repr(exc)})

