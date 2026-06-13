from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .snapshot import stable_snapshot_id


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def contains_screen_point(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    process_id: int
    process_name: str
    class_name: str
    rect: Rect
    visible: bool
    minimized: bool
    client_rect: Rect | None = None

    def window_ref(self) -> dict[str, Any]:
        return {
            "id": self.hwnd,
            "hwnd": self.hwnd,
            "app": self.process_name,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "title": self.title,
            "class_name": self.class_name,
            "snapshot_id": self.snapshot_id(),
        }

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.hwnd,
            "app": self.process_name,
            "hwnd": self.hwnd,
            "title": self.title,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "class_name": self.class_name,
            "rect": self.rect.to_dict(),
            "visible": self.visible,
            "minimized": self.minimized,
        }
        if self.client_rect is not None:
            payload["client_rect"] = self.client_rect.to_dict()
        payload["snapshot_id"] = self.snapshot_id()
        payload["window_ref"] = self.window_ref()
        return payload

    def snapshot_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "hwnd": self.hwnd,
            "title": self.title,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "class_name": self.class_name,
            "rect": self.rect.to_dict(),
            "visible": self.visible,
            "minimized": self.minimized,
        }
        if self.client_rect is not None:
            payload["client_rect"] = self.client_rect.to_dict()
        return payload

    def snapshot_id(self) -> str:
        return stable_snapshot_id(self.snapshot_payload())
