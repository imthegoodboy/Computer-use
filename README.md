# Desktop Control Tool

Windows desktop-control MVP for agents. It follows the architecture in `.agents/architecture/skill.md`: agents talk to a narrow local tool API, actions are window-scoped, state is verified after actions, and risky targets are blocked by policy.

This project is an independent implementation. It does not decompile or depend on Codex's private native Computer Use helper.

## Capabilities

- List visible desktop windows.
- List launchable Start Menu apps and running window-owning apps.
- Launch apps by id, display name, process name, shortcut, or executable path.
- Observe the current foreground window or a selected window by query/ref and return visual agent state.
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
- Run an agent observe/action/observe loop in one CLI/RPC call with trace timings.
- Block terminal, credential, password-manager, security, and agent-host targets by default.
- Optionally require explicit app/window approvals before control actions.
- Install as an npm CLI package with `desktop-control` and `desktop-control-tool` binaries.
- Keep a warm JSON-RPC stdio process for agent integrations.
- Keep a warm length-prefixed JSON-RPC named-pipe process for Windows agent integrations.
- Write structured JSONL audit logs when `DESKTOP_CONTROL_AUDIT_LOG` is set.

## Quick Start

Run commands from the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m desktop_control list-windows --pretty
python -m desktop_control list-apps --query notepad --pretty
python -m desktop_control observe --query notepad --pretty
python -m desktop_control get-window --window-id 123456 --pretty
python -m desktop_control get-window-state --window-id 123456 --pretty
```

Find a safe window such as Notepad, then use its `hwnd`:

```powershell
python -m desktop_control state --window-id 123456 --include-ui --pretty
python -m desktop_control get-window-state --window-id 123456 --include-text --pretty
python -m desktop_control screenshot --window-id 123456 --out .tmp\notepad.png --backend auto --pretty
python -m desktop_control click --window-id 123456 --x 120 --y 90 --expect-snapshot-id <snapshot_id> --pretty
python -m desktop_control double-click --window-id 123456 --x 120 --y 90 --pretty
python -m desktop_control find-elements --window-id 123456 --name-contains "Save" --pretty
python -m desktop_control wait-element --window-id 123456 --name "OK" --control-type button --timeout 5 --pretty
python -m desktop_control recover-window --ref-file .tmp\window-ref.json --pretty
python -m desktop_control click-element --window-id 123456 --name "OK" --control-type button --pretty
python -m desktop_control type-text --window-id 123456 --text "hello from desktop-control" --pretty
python -m desktop_control press-key --window-id 123456 --keys ctrl+a --keys backspace --pretty
python -m desktop_control key --window-id 123456 --keys ctrl+a --keys backspace --pretty
python -m desktop_control agent-run --query notepad --pretty
python -m desktop_control launch-app --app notepad.exe --wait-query Notepad --pretty
```

Coordinates are window-relative by default. Use `--space client` for client-area coordinates or `--space screen` for absolute screen coordinates.
`observe` and `get-window-state` capture a screenshot by default for agent visual grounding; set `DESKTOP_CONTROL_CAPTURE_DIR` or pass `--out` to choose where screenshots are written.

## Agent Observe Flow

Use `observe` as the first visual step. It selects exactly one target window by query, saved `window_ref`, explicit id, or the current foreground window when no selector is provided. It returns the canonical `window`, current `snapshot_id`, screenshot metadata, and optional UI Automation text in one JSON payload.

```powershell
desktop-control observe --query notepad --include-text --pretty
desktop-control view --ref-file .tmp\window-ref.json --pretty
desktop-control observe --pretty
```

If a query matches multiple windows, `observe` fails with `ambiguous_window` and returns candidate summaries. Pass a more specific query or use a saved `window_ref`; use `--allow-ambiguous` only when the first deterministic match is acceptable.

After observing, use the returned `window.id` for actions and pass the returned `window.snapshot_id` to `--expect-snapshot-id` for coordinate actions:

```powershell
desktop-control click --window-id 123456 --x 120 --y 90 --expect-snapshot-id <snapshot_id> --pretty
desktop-control key --window-id 123456 --keys ctrl+a --keys backspace --pretty
desktop-control observe --window-id 123456 --pretty
```

For the default agent loop, use `agent-run`. It observes the target window first, injects the observed window context into the actions, runs the actions immediately, then observes again so the caller gets the next visual state and trace timings in one payload:

```json
{
  "query": "notepad",
  "space": "client",
  "actions": [
    {"type": "click", "x": 120, "y": 90, "button": "left"},
    {"type": "type", "text": "hello"},
    {"type": "keypress", "keys": ["enter"]}
  ]
}
```

```powershell
desktop-control agent-run --file .tmp\agent-run.json --pretty
```

Pass `observe_after: false` or `--no-observe-after` only when the caller intentionally wants to skip verification. Set `strict_snapshot: true` when the caller wants geometry-level stale-coordinate rejection inside `agent-run`. Use `agent-step` when the caller already has a fresh observation and wants only to execute actions:

```json
{
  "window": {"id": 123456, "snapshot_id": "<snapshot_id>"},
  "space": "client",
  "actions": [
    {"type": "click", "x": 120, "y": 90, "button": "left"},
    {"type": "type", "text": "hello"},
    {"type": "keypress", "keys": ["enter"]}
  ],
  "observe_after": true
}
```

```powershell
desktop-control agent-step --file .tmp\agent-step.json --pretty
```

Supported agent action types match the common computer-use loop shape: `click`, `double_click`, `scroll`, `type`, `wait`, `keypress`, `drag`, `move`, and `screenshot`. `agent-run` injects the observed window context and verifies with a fresh observation; `agent-step` injects the observed window and snapshot guard into each action unless an action overrides them.

## NPM CLI Package

The npm package installs thin Node launchers for the Python CLI. Command behavior stays in `src/desktop_control`; the wrapper only finds Python, sets `PYTHONPATH`, and forwards arguments without a shell.

```powershell
npm install -g .
desktop-control --version
desktop-control list-windows --pretty
desktop-control observe --query notepad --pretty
desktop-control-tool get-window-state --window-id 123456 --pretty
```

For local development without global install:

```powershell
node .\npm\bin\desktop-control.js --npm-wrapper-doctor
node .\npm\bin\desktop-control.js list-apps --query notepad --pretty
```

Wrapper configuration:

- `DESKTOP_CONTROL_PYTHON`: absolute Python executable or launcher name.
- `DESKTOP_CONTROL_PYTHON_ARGS`: extra Python launcher args such as `-X utf8`.
- `DESKTOP_CONTROL_PACKAGE_ROOT`: override package root detection.
- `DESKTOP_CONTROL_PYTHONPATH_MODE`: `prepend` by default, or `append`, `replace`, `preserve`.
- `DESKTOP_CONTROL_PYTHONPATH_EXTRA`: additional paths appended to the wrapper-managed `PYTHONPATH`.

For high-throughput agents, start a warm process instead of launching Python per action:

```powershell
desktop-control serve-stdio
desktop-control serve-pipe --name desktop-control
```

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

Deployments can extend the safety policy without changing source code:

```powershell
$env:DESKTOP_CONTROL_BLOCKED_PROCESSES = "internal-admin.exe,vault.exe"
$env:DESKTOP_CONTROL_BLOCKED_TITLE_TERMS = "tenant secret,production admin"
$env:DESKTOP_CONTROL_BLOCKED_CLASS_TERMS = "credential"
$env:DESKTOP_CONTROL_POLICY_FILE = ".tmp\desktop-control-policy.json"
```

The optional policy file is JSON:

```json
{
  "blocked_process_names": ["internal-admin.exe"],
  "blocked_title_terms": ["Tenant Secret"],
  "blocked_class_terms": ["Credential"]
}
```

These settings add to the built-in hard denials; they do not remove protections for terminals, credential prompts, password managers, security tools, or agent-host apps.

## Agent JSON-RPC Mode

For lower overhead, keep one process alive:

```powershell
$env:PYTHONPATH = "src"
python -m desktop_control serve-stdio
```

Send one JSON-RPC request per line:

```json
{"jsonrpc":"2.0","id":1,"method":"observe","params":{"query":"notepad","include_text":true}}
```

Supported methods are `list_apps`, `launch_app`, `list_windows`, `observe`, `view`, `agent_run`, `run`, `agent_step`, `act`, `perform_actions`, `get_window`, `activate_window`, `get_window_state`, `state`, `screenshot`, `click`, `double_click`, `move`, `scroll`, `drag`, `type_text`, `type`, `key`, `press_key`, `keypress`, `find_elements`, `click_element`, `invoke_element`, `perform_secondary_action`, `set_element_value`, `set_value`, `wait`, `wait_window`, `wait_element`, `recover_window`, and `batch`.

## Named-Pipe JSON-RPC

For a local Windows helper process closer to Codex Computer Use's native transport, use length-prefixed JSON-RPC over a named pipe:

```powershell
python -m desktop_control serve-pipe --name desktop-control
python -m desktop_control pipe-request --name desktop-control --request-file .tmp\request.json --pretty
```

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

The JSON-RPC method name is `batch` with the same payload shape. Nested batches are rejected. For flexible integrations, most methods accept either `window_id` or a Codex-style `window` object containing `id`/`hwnd` and `app`.

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

For agent visual observation:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_observe.ps1
```

For agent action-step execution:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_agent_step.ps1
```

For the full agent observe/action/observe loop:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_agent_run.ps1
```

For app launch:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_launch.ps1
```

For named-pipe transport:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_pipe.ps1
```

For npm CLI packaging:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_npm_cli.ps1
```

For stale-window recovery:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_recovery.ps1
```
