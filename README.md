# Desktop Control Tool

Windows desktop-control MVP for agents. It follows the architecture in `.agents/architecture/skill.md`: agents talk to a narrow local tool API, actions are window-scoped, state is verified after actions, and risky targets are blocked by policy.

This project is an independent implementation. It does not decompile or depend on Codex's private native Computer Use helper.

## Capabilities

- List visible desktop windows.
- List launchable Start Menu apps and running window-owning apps.
- Launch apps by id, display name, process name, shortcut, or executable path.
- Capture window state as JSON.
- Capture a window screenshot.
- Capture screenshots through selectable `auto`, `mss`, or `pil` backends with checksum and nonblank metadata.
- Optionally include UI metadata from Windows UI Automation or child HWND fallback.
- Activate a target window.
- Move, click, drag, scroll, type text, and press key chords.
- Find, click, invoke, and set values on Windows UI Automation elements.
- Wait for matching windows or UI Automation elements without blind sleeps.
- Reject stale action coordinates when an expected `snapshot_id` no longer matches current window state.
- Return a reusable `window_ref` and recover a current window when the original handle is stale.
- Batch multiple actions in one CLI/RPC call for lower overhead.
- Block terminal, credential, password-manager, security, and agent-host targets by default.
- Optionally require explicit app/window approvals before control actions.
- Keep a warm JSON-RPC stdio process for agent integrations.
- Write structured JSONL audit logs when `DESKTOP_CONTROL_AUDIT_LOG` is set.

## Quick Start

Run commands from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m desktop_control list-windows --pretty
python -m desktop_control list-apps --query notepad --pretty
```

Find a safe window such as Notepad, then use its `hwnd`:

```powershell
python -m desktop_control state --window-id 123456 --include-ui --pretty
python -m desktop_control screenshot --window-id 123456 --out .tmp\notepad.png --backend auto --pretty
python -m desktop_control click --window-id 123456 --x 120 --y 90 --expect-snapshot-id <snapshot_id> --pretty
python -m desktop_control find-elements --window-id 123456 --name-contains "Save" --pretty
python -m desktop_control wait-element --window-id 123456 --name "OK" --control-type button --timeout 5 --pretty
python -m desktop_control recover-window --ref-file .tmp\window-ref.json --pretty
python -m desktop_control click-element --window-id 123456 --name "OK" --control-type button --pretty
python -m desktop_control type-text --window-id 123456 --text "hello from desktop-control" --pretty
python -m desktop_control key --window-id 123456 --keys ctrl+a --keys backspace --pretty
python -m desktop_control launch-app --app notepad.exe --wait-query Notepad --pretty
```

Coordinates are window-relative by default. Use `--space client` for client-area coordinates or `--space screen` for absolute screen coordinates.

## App Approvals

Default mode blocks dangerous targets but allows ordinary safe windows. To require explicit approval before control actions:

```powershell
$env:DESKTOP_CONTROL_REQUIRE_APPROVALS = "1"
$env:DESKTOP_CONTROL_APPROVALS_FILE = ".tmp\desktop-control-approvals.json"
python -m desktop_control approve-app --process-name notepad.exe --pretty
```

You can also approve a specific discovered window:

```powershell
python -m desktop_control approve-window --window-id 123456 --pretty
python -m desktop_control list-approvals --pretty
```

`DESKTOP_CONTROL_APPROVED_APPS` can hold a comma-separated process allowlist for short-lived sessions, for example `notepad.exe,calc.exe`. Blocked sensitive targets remain blocked even when listed.

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

Supported methods are `list_apps`, `launch_app`, `list_windows`, `state`, `screenshot`, `click`, `move`, `scroll`, `drag`, `type_text`, `key`, `find_elements`, `click_element`, `invoke_element`, `set_element_value`, `wait_window`, `wait_element`, `recover_window`, and `batch`.

## App Discovery And Launch

`list-apps` combines Start Menu shortcuts with running apps that own visible top-level windows. Each app includes an `app_ref`, launch path metadata, process ids, running state, and windows when requested.

```powershell
python -m desktop_control list-apps --query notepad --pretty
python -m desktop_control launch-app --app notepad.exe --wait-query Notepad --pretty
```

`launch-app` uses Windows shell execution and applies the same hard blocklist for terminal, security, credential, password-manager, and agent-host apps.

## Window Recovery

Every window payload includes a `window_ref` with `hwnd`, process metadata, title, class name, and snapshot id. If a later action fails because the `hwnd` is stale, recover the current window explicitly:

```powershell
python -m desktop_control state --window-id 123456 --pretty
python -m desktop_control recover-window --process-name notepad.exe --title "Untitled - Notepad" --pretty
```

The resolver validates the original `hwnd` when possible, then falls back to visible windows that match process/title/class identity. Ambiguous matches fail unless `--allow-ambiguous` is passed.

## Batch Actions

Batch related actions to avoid process startup or RPC round trips for every step:

```json
{
  "actions": [
    {"method": "move", "params": {"window_id": 123456, "space": "client", "x": 140, "y": 130}},
    {"method": "click", "params": {"window_id": 123456, "space": "client", "x": 160, "y": 150}}
  ]
}
```

Run it:

```powershell
python -m desktop_control batch --file .tmp\batch-actions.json --pretty
```

The JSON-RPC method name is `batch` with the same payload shape. Nested batches are rejected.

## Audit Logs

Set `DESKTOP_CONTROL_AUDIT_LOG` to capture JSONL receipts for CLI and RPC actions:

```powershell
$env:DESKTOP_CONTROL_AUDIT_LOG = ".tmp\desktop-control-audit.jsonl"
```

The audit log records action name, source, status, parameters, result summary, and structured errors. Sensitive text-like fields such as `text`, `value`, `password`, `secret`, and `token` are redacted with length metadata.

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

Or run the automated mouse smoke:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_mouse.ps1
```

For UI Automation element actions:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_uia.ps1
```

For wait predicates:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_wait.ps1
```

For approval enforcement:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_approvals.ps1
```

For stale-snapshot guards:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_snapshot.ps1
```

For batched actions:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_batch.ps1
```

For capture reliability:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_capture.ps1
```

For app launch:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_launch.ps1
```

For stale-window recovery:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_recovery.ps1
```
