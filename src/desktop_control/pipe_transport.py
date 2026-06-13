from __future__ import annotations

import json
import struct
import time
from typing import Any, Callable

from .errors import DesktopControlError, wrap_os_error

FRAME_HEADER_SIZE = 4
MAX_FRAME_BYTES = 16 * 1024 * 1024


def pipe_path(name: str) -> str:
    value = name.strip()
    if not value:
        raise DesktopControlError("invalid_pipe_name", "Pipe name cannot be empty")
    if value.startswith("\\\\.\\pipe\\"):
        return value
    if "\\" in value or "/" in value:
        raise DesktopControlError("invalid_pipe_name", "Pipe name must be a simple name or full \\\\.\\pipe\\ path")
    return f"\\\\.\\pipe\\{value}"


def encode_frame(payload: Any) -> bytes:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_FRAME_BYTES:
        raise DesktopControlError(
            "frame_too_large",
            "JSON-RPC frame is too large",
            {"bytes": len(data), "max_bytes": MAX_FRAME_BYTES},
        )
    return struct.pack("<I", len(data)) + data


def _read_exact(read_chunk: Callable[[int], bytes], size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = read_chunk(remaining)
        if not chunk:
            raise EOFError("pipe closed while reading frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(read_chunk: Callable[[int], bytes]) -> Any:
    header = _read_exact(read_chunk, FRAME_HEADER_SIZE)
    (size,) = struct.unpack("<I", header)
    if size > MAX_FRAME_BYTES:
        raise DesktopControlError(
            "frame_too_large",
            "JSON-RPC frame is too large",
            {"bytes": size, "max_bytes": MAX_FRAME_BYTES},
        )
    data = _read_exact(read_chunk, size)
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DesktopControlError("invalid_frame_json", "Frame payload is not valid JSON", {"details": str(exc)}) from exc


def serve_pipe(name: str) -> int:
    import pywintypes
    import win32file
    import win32pipe
    import winerror

    from .rpc import handle_rpc_payload

    path = pipe_path(name)
    while True:
        handle = win32pipe.CreateNamedPipe(
            path,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            MAX_FRAME_BYTES,
            MAX_FRAME_BYTES,
            0,
            None,
        )
        try:
            try:
                win32pipe.ConnectNamedPipe(handle, None)
            except pywintypes.error as exc:
                if exc.winerror != winerror.ERROR_PIPE_CONNECTED:
                    raise

            def read_chunk(size: int) -> bytes:
                try:
                    _error, data = win32file.ReadFile(handle, size)
                    return bytes(data)
                except pywintypes.error as exc:
                    if exc.winerror in {winerror.ERROR_BROKEN_PIPE, winerror.ERROR_PIPE_NOT_CONNECTED}:
                        return b""
                    raise

            while True:
                try:
                    request = read_frame(read_chunk)
                except EOFError:
                    break
                response = handle_rpc_payload(request)
                if response is not None:
                    win32file.WriteFile(handle, encode_frame(response))
        except DesktopControlError:
            raise
        except Exception as exc:
            raise wrap_os_error("pipe_server_failed", "Named-pipe server failed", exc) from exc
        finally:
            try:
                win32pipe.DisconnectNamedPipe(handle)
            except Exception:
                pass
            win32file.CloseHandle(handle)


def pipe_request(name: str, payload: Any, timeout_seconds: float = 10.0) -> Any:
    import pywintypes
    import win32con
    import win32file
    import win32pipe
    import winerror

    path = pipe_path(name)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    handle = None
    while True:
        try:
            handle = win32file.CreateFile(
                path,
                win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                0,
                None,
                win32con.OPEN_EXISTING,
                0,
                None,
            )
            break
        except pywintypes.error as exc:
            if exc.winerror not in {winerror.ERROR_PIPE_BUSY, winerror.ERROR_FILE_NOT_FOUND}:
                raise wrap_os_error("pipe_connect_failed", "Could not connect to named pipe", exc) from exc
            if time.monotonic() >= deadline:
                raise DesktopControlError(
                    "pipe_connect_timeout",
                    "Timed out connecting to named pipe",
                    {"pipe": path, "timeout_seconds": timeout_seconds},
                ) from exc
            time.sleep(0.05)

    try:
        win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_BYTE, None, None)
        win32file.WriteFile(handle, encode_frame(payload))

        def read_chunk(size: int) -> bytes:
            _error, data = win32file.ReadFile(handle, size)
            return bytes(data)

        return read_frame(read_chunk)
    except DesktopControlError:
        raise
    except Exception as exc:
        raise wrap_os_error("pipe_request_failed", "Named-pipe request failed", exc) from exc
    finally:
        if handle is not None:
            win32file.CloseHandle(handle)
