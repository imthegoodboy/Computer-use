import io
import struct

import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.pipe_transport import MAX_FRAME_BYTES, encode_frame, pipe_path, read_frame


def test_pipe_path_accepts_simple_name():
    assert pipe_path("desktop-control-test") == "\\\\.\\pipe\\desktop-control-test"


def test_pipe_path_rejects_empty_name():
    with pytest.raises(DesktopControlError) as exc_info:
        pipe_path("")
    assert exc_info.value.code == "invalid_pipe_name"


def test_length_prefixed_frame_round_trips_json_payload():
    payload = {"jsonrpc": "2.0", "id": 1, "method": "list_windows", "params": {"query": "none"}}
    stream = io.BytesIO(encode_frame(payload))

    assert read_frame(stream.read) == payload


def test_read_frame_rejects_oversized_payload():
    stream = io.BytesIO(struct.pack("<I", MAX_FRAME_BYTES + 1))

    with pytest.raises(DesktopControlError) as exc_info:
        read_frame(stream.read)

    assert exc_info.value.code == "frame_too_large"
