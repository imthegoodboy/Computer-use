from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .capture import capture_window
from .errors import DesktopControlError
from .input import click_at, drag_at, move_to, press_key_sequence, scroll_at, send_text
from .policy import assert_allowed_target
from .uia import get_uia_tree
from .windows import (
    CoordinateSpace,
    activate_window,
    get_window,
    list_windows,
    require_point_in_window,
    resolve_point,
)


def _json_dump(payload: dict[str, Any], pretty: bool) -> str:
    return json.dumps(payload, indent=2 if pretty else None, sort_keys=pretty)


def _print(payload: dict[str, Any], pretty: bool) -> None:
    print(_json_dump(payload, pretty))


def _space(value: str) -> CoordinateSpace:
    if value not in {"window", "client", "screen"}:
        raise argparse.ArgumentTypeError("space must be one of: window, client, screen")
    return value  # type: ignore[return-value]


def _window_for_action(hwnd: int, action: str, activate: bool = True):
    window = get_window(hwnd)
    assert_allowed_target(window, action)
    if activate:
        window = activate_window(hwnd)
        assert_allowed_target(window, action)
    return window


def _resolve_checked_point(hwnd: int, x: int, y: int, space: CoordinateSpace) -> tuple[int, int]:
    screen_x, screen_y = resolve_point(hwnd, x, y, space)
    require_point_in_window(hwnd, screen_x, screen_y)
    return screen_x, screen_y


def command_list_windows(args: argparse.Namespace) -> dict[str, Any]:
    windows = list_windows(include_hidden=args.include_hidden, query=args.query)
    return {
        "ok": True,
        "version": __version__,
        "windows": [window.to_dict() for window in windows],
    }


def command_state(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "state", activate=args.activate)
    payload: dict[str, Any] = {
        "ok": True,
        "window": window.to_dict(),
    }
    if args.screenshot:
        payload["screenshot"] = capture_window(args.window_id, args.screenshot)
    if args.include_ui:
        payload["ui"] = get_uia_tree(args.window_id, max_depth=args.max_depth, max_nodes=args.max_nodes)
    return payload


def command_screenshot(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "screenshot", activate=args.activate)
    return {
        "ok": True,
        "window": window.to_dict(),
        "screenshot": capture_window(args.window_id, args.out),
    }


def command_click(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "click", activate=not args.no_activate)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    click_at(x, y, button=args.button, count=args.count)
    return {
        "ok": True,
        "action": "click",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
        "button": args.button,
        "count": args.count,
    }


def command_move(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "move", activate=not args.no_activate)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    move_to(x, y)
    return {
        "ok": True,
        "action": "move",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
    }


def command_scroll(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "scroll", activate=not args.no_activate)
    x, y = _resolve_checked_point(args.window_id, args.x, args.y, args.space)
    scroll_at(x, y, args.delta)
    return {
        "ok": True,
        "action": "scroll",
        "window": window.to_dict(),
        "screen_point": {"x": x, "y": y},
        "delta": args.delta,
    }


def command_drag(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "drag", activate=not args.no_activate)
    from_x, from_y = _resolve_checked_point(args.window_id, args.from_x, args.from_y, args.space)
    to_x, to_y = _resolve_checked_point(args.window_id, args.to_x, args.to_y, args.space)
    drag_at(
        from_x,
        from_y,
        to_x,
        to_y,
        button=args.button,
        duration_seconds=args.duration,
        steps=args.steps,
    )
    return {
        "ok": True,
        "action": "drag",
        "window": window.to_dict(),
        "from": {"x": from_x, "y": from_y},
        "to": {"x": to_x, "y": to_y},
        "button": args.button,
    }


def command_type_text(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "type_text", activate=not args.no_activate)
    text = args.text
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    send_text(text, method=args.method)
    return {
        "ok": True,
        "action": "type_text",
        "window": window.to_dict(),
        "characters": len(text),
        "method": args.method,
    }


def command_key(args: argparse.Namespace) -> dict[str, Any]:
    window = _window_for_action(args.window_id, "key", activate=not args.no_activate)
    press_key_sequence(args.keys)
    return {
        "ok": True,
        "action": "key",
        "window": window.to_dict(),
        "keys": args.keys,
    }


def command_serve_stdio(args: argparse.Namespace) -> int:
    from .rpc import serve_stdio

    return serve_stdio()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop-control")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-windows", help="List visible top-level windows")
    list_parser.add_argument("--include-hidden", action="store_true")
    list_parser.add_argument("--query", help="Filter by title or process name")
    list_parser.add_argument("--pretty", action="store_true")
    list_parser.set_defaults(func=command_list_windows)

    state_parser = subparsers.add_parser("state", help="Get window state")
    state_parser.add_argument("--window-id", type=int, required=True)
    state_parser.add_argument("--include-ui", action="store_true")
    state_parser.add_argument("--max-depth", type=int, default=3)
    state_parser.add_argument("--max-nodes", type=int, default=200)
    state_parser.add_argument("--screenshot", help="Optional screenshot output path")
    state_parser.add_argument("--activate", action="store_true")
    state_parser.add_argument("--pretty", action="store_true")
    state_parser.set_defaults(func=command_state)

    screenshot_parser = subparsers.add_parser("screenshot", help="Capture a window screenshot")
    screenshot_parser.add_argument("--window-id", type=int, required=True)
    screenshot_parser.add_argument("--out", required=True)
    screenshot_parser.add_argument("--activate", action="store_true")
    screenshot_parser.add_argument("--pretty", action="store_true")
    screenshot_parser.set_defaults(func=command_screenshot)

    click_parser = subparsers.add_parser("click", help="Click a window-relative point")
    click_parser.add_argument("--window-id", type=int, required=True)
    click_parser.add_argument("--x", type=int, required=True)
    click_parser.add_argument("--y", type=int, required=True)
    click_parser.add_argument("--space", type=_space, default="window")
    click_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    click_parser.add_argument("--count", type=int, default=1)
    click_parser.add_argument("--no-activate", action="store_true")
    click_parser.add_argument("--pretty", action="store_true")
    click_parser.set_defaults(func=command_click)

    move_parser = subparsers.add_parser("move", help="Move the cursor to a window-relative point")
    move_parser.add_argument("--window-id", type=int, required=True)
    move_parser.add_argument("--x", type=int, required=True)
    move_parser.add_argument("--y", type=int, required=True)
    move_parser.add_argument("--space", type=_space, default="window")
    move_parser.add_argument("--no-activate", action="store_true")
    move_parser.add_argument("--pretty", action="store_true")
    move_parser.set_defaults(func=command_move)

    scroll_parser = subparsers.add_parser("scroll", help="Scroll at a point")
    scroll_parser.add_argument("--window-id", type=int, required=True)
    scroll_parser.add_argument("--x", type=int, required=True)
    scroll_parser.add_argument("--y", type=int, required=True)
    scroll_parser.add_argument("--space", type=_space, default="window")
    scroll_parser.add_argument("--delta", type=int, required=True, help="Wheel ticks; positive scrolls up")
    scroll_parser.add_argument("--no-activate", action="store_true")
    scroll_parser.add_argument("--pretty", action="store_true")
    scroll_parser.set_defaults(func=command_scroll)

    drag_parser = subparsers.add_parser("drag", help="Drag between two points")
    drag_parser.add_argument("--window-id", type=int, required=True)
    drag_parser.add_argument("--from-x", type=int, required=True)
    drag_parser.add_argument("--from-y", type=int, required=True)
    drag_parser.add_argument("--to-x", type=int, required=True)
    drag_parser.add_argument("--to-y", type=int, required=True)
    drag_parser.add_argument("--space", type=_space, default="window")
    drag_parser.add_argument("--button", choices=["left", "right", "middle"], default="left")
    drag_parser.add_argument("--duration", type=float, default=0.2)
    drag_parser.add_argument("--steps", type=int, default=12)
    drag_parser.add_argument("--no-activate", action="store_true")
    drag_parser.add_argument("--pretty", action="store_true")
    drag_parser.set_defaults(func=command_drag)

    type_parser = subparsers.add_parser("type-text", help="Type text into a window")
    type_parser.add_argument("--window-id", type=int, required=True)
    type_parser.add_argument("--text", default="")
    type_parser.add_argument("--text-file")
    type_parser.add_argument("--method", choices=["clipboard", "unicode"], default="clipboard")
    type_parser.add_argument("--no-activate", action="store_true")
    type_parser.add_argument("--pretty", action="store_true")
    type_parser.set_defaults(func=command_type_text)

    key_parser = subparsers.add_parser("key", help="Press key chords")
    key_parser.add_argument("--window-id", type=int, required=True)
    key_parser.add_argument("--keys", action="append", required=True, help="Example: ctrl+a, enter, alt+f4")
    key_parser.add_argument("--no-activate", action="store_true")
    key_parser.add_argument("--pretty", action="store_true")
    key_parser.set_defaults(func=command_key)

    serve_parser = subparsers.add_parser("serve-stdio", help="Run JSON-RPC over stdin/stdout")
    serve_parser.set_defaults(func=command_serve_stdio)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        if isinstance(payload, int):
            return payload
        _print(payload, pretty=bool(getattr(args, "pretty", False)))
        return 0
    except DesktopControlError as exc:
        print(_json_dump(exc.to_dict(), pretty=True), file=sys.stderr)
        return 2
