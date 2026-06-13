from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Literal

from PIL import Image, ImageGrab

from .errors import DesktopControlError
from .windows import get_window

CaptureBackend = Literal["auto", "pil", "mss"]
CAPTURE_DIR_ENV = "DESKTOP_CONTROL_CAPTURE_DIR"
DEFAULT_CAPTURE_DIR = ".tmp/desktop-control-captures"


def default_capture_path(hwnd: int, suffix: str = ".png") -> Path:
    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    root = Path(os.environ.get(CAPTURE_DIR_ENV, DEFAULT_CAPTURE_DIR))
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    nonce = f"{time.time_ns() % 1_000_000_000:09d}"
    return root / f"window-{int(hwnd)}-{timestamp}-{nonce}{normalized_suffix}"


def _capture_pil(bbox: tuple[int, int, int, int]) -> Image.Image:
    return ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")


def _capture_mss(bbox: tuple[int, int, int, int]) -> Image.Image:
    try:
        import mss
    except ImportError as exc:
        raise DesktopControlError("capture_backend_unavailable", "mss capture backend is not installed") from exc

    left, top, right, bottom = bbox
    with mss.mss() as capture:
        raw = capture.grab(
            {
                "left": int(left),
                "top": int(top),
                "width": int(right - left),
                "height": int(bottom - top),
            }
        )
    return Image.frombytes("RGB", raw.size, raw.rgb)


def _image_metadata(image: Image.Image, path: Path) -> dict[str, object]:
    data = path.read_bytes()
    extrema = image.getextrema()
    nonblank = any(channel_min != channel_max for channel_min, channel_max in extrema)
    sample = image.copy()
    sample.thumbnail((64, 64))
    unique_sample_colors = len(set(sample.getdata()))
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "nonblank": nonblank,
        "unique_sample_colors": unique_sample_colors,
        "channel_extrema": [
            {"min": int(channel_min), "max": int(channel_max)}
            for channel_min, channel_max in extrema
        ],
    }


def _capture_with_backend(
    bbox: tuple[int, int, int, int],
    backend: CaptureBackend,
) -> tuple[Image.Image, str, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    backends = ["mss", "pil"] if backend == "auto" else [backend]
    for candidate in backends:
        try:
            if candidate == "mss":
                return _capture_mss(bbox), candidate, errors
            if candidate == "pil":
                return _capture_pil(bbox), candidate, errors
        except Exception as exc:
            errors.append({"backend": candidate, "error": repr(exc)})
            continue
    raise DesktopControlError(
        "capture_failed",
        "All capture backends failed",
        {"backend": backend, "attempt_errors": errors},
    )


def capture_window(
    hwnd: int,
    out_path: str | Path,
    backend: CaptureBackend = "auto",
) -> dict[str, object]:
    if backend not in {"auto", "pil", "mss"}:
        raise DesktopControlError("invalid_capture_backend", f"Unsupported capture backend: {backend}")
    window = get_window(hwnd)
    if window.minimized:
        raise DesktopControlError("capture_failed", "Cannot capture a minimized window", window.to_dict())
    if window.rect.width <= 0 or window.rect.height <= 0:
        raise DesktopControlError("capture_failed", "Window has an empty rectangle", window.to_dict())

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bbox = (window.rect.left, window.rect.top, window.rect.right, window.rect.bottom)
    image, resolved_backend, attempt_errors = _capture_with_backend(bbox, backend)
    image.save(path)
    return {
        "path": str(path),
        "backend": resolved_backend,
        "requested_backend": backend,
        "width": image.width,
        "height": image.height,
        "bbox": {
            "left": bbox[0],
            "top": bbox[1],
            "right": bbox[2],
            "bottom": bbox[3],
        },
        "window_snapshot_id": window.snapshot_id(),
        "image": _image_metadata(image, path),
        "fallback_errors": attempt_errors,
    }

