from __future__ import annotations

from pathlib import Path

from PIL import ImageGrab

from .errors import DesktopControlError
from .windows import get_window


def capture_window(hwnd: int, out_path: str | Path) -> dict[str, object]:
    window = get_window(hwnd)
    if window.minimized:
        raise DesktopControlError("capture_failed", "Cannot capture a minimized window", window.to_dict())
    if window.rect.width <= 0 or window.rect.height <= 0:
        raise DesktopControlError("capture_failed", "Window has an empty rectangle", window.to_dict())

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bbox = (window.rect.left, window.rect.top, window.rect.right, window.rect.bottom)
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    image.save(path)
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "bbox": {
            "left": bbox[0],
            "top": bbox[1],
            "right": bbox[2],
            "bottom": bbox[3],
        },
    }

