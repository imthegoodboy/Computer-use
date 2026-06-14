from pathlib import Path

from PIL import Image
import pytest

from desktop_control.capture import CAPTURE_DIR_ENV, _image_metadata, capture_window, default_capture_path
from desktop_control.errors import DesktopControlError


def test_image_metadata_marks_nonblank_image(tmp_path):
    path = tmp_path / "image.png"
    image = Image.new("RGB", (10, 10), "white")
    image.putpixel((5, 5), (0, 0, 0))
    image.save(path)

    metadata = _image_metadata(image, path)
    assert metadata["bytes"] > 0
    assert metadata["nonblank"] is True
    assert metadata["unique_sample_colors"] >= 2
    assert len(metadata["sha256"]) == 64


def test_image_metadata_marks_blank_image(tmp_path):
    path = tmp_path / "blank.png"
    image = Image.new("RGB", (10, 10), "white")
    image.save(path)

    metadata = _image_metadata(image, path)
    assert metadata["nonblank"] is False


def test_capture_rejects_invalid_backend():
    with pytest.raises(DesktopControlError) as exc_info:
        capture_window(1, Path("unused.png"), backend="bad")  # type: ignore[arg-type]
    assert exc_info.value.code == "invalid_capture_backend"


def test_default_capture_path_uses_configurable_directory(monkeypatch, tmp_path):
    monkeypatch.setenv(CAPTURE_DIR_ENV, str(tmp_path))

    path = default_capture_path(123)

    assert path.parent == tmp_path
    assert path.name.startswith("window-123-")
    assert path.suffix == ".png"


def test_capture_window_can_embed_data_url(monkeypatch, tmp_path):
    from desktop_control import capture
    from desktop_control.models import Rect, WindowInfo

    target = WindowInfo(
        hwnd=1,
        title="Target",
        process_id=10,
        process_name="target.exe",
        class_name="TargetWindow",
        rect=Rect(0, 0, 10, 10),
        visible=True,
        minimized=False,
    )
    image = Image.new("RGB", (10, 10), "white")
    image.putpixel((5, 5), (0, 0, 0))

    monkeypatch.setattr(capture, "get_window", lambda hwnd: target)
    monkeypatch.setattr(capture, "_capture_with_backend", lambda bbox, backend: (image, "test", []))

    payload = capture_window(1, tmp_path / "shot.png", include_image_data=True)

    assert payload["mime_type"] == "image/png"
    assert str(payload["url"]).startswith("data:image/png;base64,")
    assert payload["image"]["bytes"] > 0
