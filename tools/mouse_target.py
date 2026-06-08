from __future__ import annotations

import argparse
import json
import time
import tkinter as tk
from pathlib import Path


def write_event(log_path: Path, event_type: str, event: tk.Event) -> None:
    payload = {
        "type": event_type,
        "time": time.time(),
        "x": int(getattr(event, "x", 0)),
        "y": int(getattr(event, "y", 0)),
        "x_root": int(getattr(event, "x_root", 0)),
        "y_root": int(getattr(event, "y_root", 0)),
        "button": int(getattr(event, "num", 0) or 0),
        "delta": int(getattr(event, "delta", 0) or 0),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--ready", required=True)
    args = parser.parse_args()

    log_path = Path(args.log)
    ready_path = Path(args.ready)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    root = tk.Tk()
    root.title(args.title)
    root.geometry("560x420+220+160")
    root.minsize(400, 300)

    canvas = tk.Canvas(root, background="#f7f7f7", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.create_text(
        24,
        24,
        anchor="nw",
        text="Mouse target",
        fill="#222222",
        font=("Segoe UI", 14, "bold"),
    )
    canvas.create_rectangle(80, 80, 480, 320, outline="#2b6cb0", width=2)
    canvas.create_text(
        100,
        100,
        anchor="nw",
        text="Click, drag, move, and scroll here.",
        fill="#333333",
        font=("Segoe UI", 10),
    )

    bindings = {
        "<Motion>": "motion",
        "<ButtonPress>": "button_press",
        "<ButtonRelease>": "button_release",
        "<B1-Motion>": "drag_motion",
        "<MouseWheel>": "mouse_wheel",
        "<Button-4>": "mouse_wheel_up",
        "<Button-5>": "mouse_wheel_down",
    }
    for sequence, event_type in bindings.items():
        canvas.bind(sequence, lambda event, kind=event_type: write_event(log_path, kind, event))

    root.after(250, root.focus_force)
    root.after(300, lambda: ready_path.write_text("ready", encoding="utf-8"))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

