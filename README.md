# Desktop Control Tool

Windows desktop-control MVP for agents. It follows the architecture in `.agents/architecture/skill.md`: agents talk to a narrow local tool API, actions are window-scoped, state is verified after actions, and risky targets are blocked by policy.

This project is an independent implementation. It does not decompile or depend on Codex's private native Computer Use helper.

## Capabilities

- List visible desktop windows.
- Capture window state as JSON.
- Capture a window screenshot.
- Optionally include UI metadata from Windows UI Automation or child HWND fallback.
- Activate a target window.
- Move, click, drag, scroll, type text, and press key chords.
- Block terminal, credential, password-manager, security, and agent-host targets by default.
- Keep a warm JSON-RPC stdio process for agent integrations.

## Quick Start

Run commands from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m desktop_control list-windows --pretty
```

Find a safe window such as Notepad, then use its `hwnd`:

```powershell
python -m desktop_control state --window-id 123456 --include-ui --pretty
python -m desktop_control screenshot --window-id 123456 --out .tmp\notepad.png --pretty
python -m desktop_control click --window-id 123456 --x 120 --y 90 --pretty
python -m desktop_control type-text --window-id 123456 --text "hello from desktop-control" --pretty
python -m desktop_control key --window-id 123456 --keys ctrl+a --keys backspace --pretty
```

Coordinates are window-relative by default. Use `--space client` for client-area coordinates or `--space screen` for absolute screen coordinates.

## Agent JSON-RPC Mode

For lower overhead, keep one process alive:

```powershell
$env:PYTHONPATH = "src"
python -m desktop_control serve-stdio
```

Send one JSON-RPC request per line:

```json
{"jsonrpc":"2.0","id":1,"method":"list_windows","params":{"query":"notepad"}}
```

Supported methods are `list_windows`, `state`, `screenshot`, `click`, `move`, `scroll`, `drag`, `type_text`, and `key`.

## Production Notes

This MVP already uses more than screenshots: Win32 window discovery, foreground control, `SendInput`, clipboard paste for fast text entry, and optional UI Automation metadata. The production architecture should add Windows Graphics Capture for unobscured window capture, app-native adapters such as browser DevTools or Office COM where available, OCR/vision parsing fallback, WinEvent hooks for wait predicates, and a user-facing approval broker.

## Safety Model

The tool refuses to automate likely dangerous targets, including terminals, password managers, security prompts, credential windows, admin/UAC prompts, and the agent host app. Keep that policy in place for production. Add a user-facing approval broker before enabling broader app access.

## Tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

For mouse-specific smoke testing, launch the local event target:

```powershell
python tools\mouse_target.py --title "DesktopControlMouseTarget" --log .tmp\mouse-events.jsonl --ready .tmp\mouse-ready.txt
```

Then drive it with `move`, `click`, `drag`, and `scroll` using `--space client`; inspect `.tmp\mouse-events.jsonl` for recorded event coordinates.
