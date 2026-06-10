from pathlib import Path

from PIL import Image
import pytest

from desktop_control.capture import _image_metadata, capture_window
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
