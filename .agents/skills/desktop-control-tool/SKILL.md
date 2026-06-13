---
name: desktop-control-tool
description: Design, build, or operate a production Windows desktop-control tool for agents, including OpenAI/Codex Computer Use style architecture, GUI automation APIs, screenshots, UI Automation, SendInput, safety approvals, fast action batching, state recovery, and agent-facing tool protocols. Use when researching, architecting, implementing, or evaluating computer-use/desktop-control systems for AI agents.
---

# Desktop Control Tool

## Overview

Use this skill when the user wants an agent to research, design, build, or use a computer-use style desktop-control tool. The canonical architecture reference is `../../architecture/skill.md`; read it before making implementation decisions. Supporting source notes are in `references/sources.md`.

## Workflow

1. Classify the task:
   - Research or architecture: read `../../architecture/skill.md` and `references/sources.md`, then answer from the evidence and design rules there.
   - Implementation: read `../../architecture/skill.md` and `references/sources.md`, then implement the smallest production-aligned slice that can be tested locally.
   - Tool operation: prefer an existing trusted desktop-control plugin/tool when available, then use this skill's operating rules.
2. Keep the tool shape close to OpenAI/Codex Computer Use:
   - App/window discovery.
   - Window-scoped state snapshots.
   - Screenshot and accessibility data.
   - Batched actions.
   - Verification after action groups.
   - Policy approval before risky UI actions.
3. Prefer robust action paths:
   - App-native APIs first.
   - UI Automation control patterns second.
   - Keyboard shortcuts third.
   - SendInput coordinates as fallback.
   - Vision/OCR fallback when UIA/app APIs are weak.
4. Treat OS and safety boundaries as design constraints:
   - Do not automate terminal apps through UI.
   - Do not automate password managers, security tools, UAC/admin prompts, or the agent host app.
   - Do not bypass browser/OS safety interstitials.
   - Ask for explicit approval before destructive, sensitive, account, financial, medical, upload, install, or third-party communication actions.

## Implementation Rules

- Build an independent helper; do not depend on Codex private helper internals.
- Use a local broker/helper process with a narrow RPC protocol.
- In this repository, the local MVP entrypoints are the npm `desktop-control` CLI wrapper and `python -m desktop_control` with `PYTHONPATH=src`.
- Make all actions target a canonical window object returned by discovery or snapshot APIs.
- Include snapshot generation ids and screenshot ids so stale element indexes and stale coordinates can be rejected.
- Add structured errors for stale handles, activation failure, policy denial, UIA failure, capture failure, and user interruption.
- Add trace logging from the first prototype.
- Test against safe apps first: Notepad, Calculator, a local browser profile, and a synthetic test app.

## Local MVP Commands

Use these from the repository root:

```powershell
npm install -g .
desktop-control --npm-wrapper-doctor
$env:PYTHONPATH = "src"
$env:DESKTOP_CONTROL_REQUIRE_APPROVALS = "1"
$env:DESKTOP_CONTROL_APPROVALS_FILE = ".tmp\desktop-control-approvals.json"
$env:DESKTOP_CONTROL_AUDIT_LOG = ".tmp\desktop-control-audit.jsonl"
desktop-control list-windows --pretty
desktop-control list-apps --query notepad --pretty
desktop-control launch-app --app notepad.exe --wait-query Notepad --pretty
desktop-control approve-app --process-name notepad.exe --pretty
desktop-control observe --query notepad --include-text --pretty
desktop-control view --ref-file .tmp\window-ref.json --pretty
desktop-control get-window --window-id <hwnd> --pretty
desktop-control activate-window --window-id <hwnd> --pretty
desktop-control get-window-state --window-id <hwnd> --include-text --pretty
desktop-control state --window-id <hwnd> --include-ui --pretty
desktop-control screenshot --window-id <hwnd> --out .tmp\window.png --backend auto --pretty
desktop-control click --window-id <hwnd> --x <x> --y <y> --expect-snapshot-id <snapshot_id> --pretty
desktop-control double-click --window-id <hwnd> --x <x> --y <y> --pretty
desktop-control find-elements --window-id <hwnd> --name-contains "Save" --pretty
desktop-control wait-window --query "Notepad" --timeout 5 --pretty
desktop-control wait-element --window-id <hwnd> --name "OK" --control-type button --timeout 5 --pretty
desktop-control recover-window --ref-file .tmp\window-ref.json --pretty
desktop-control click-element --window-id <hwnd> --name "OK" --control-type button --pretty
desktop-control set-element-value --window-id <hwnd> --control-type edit --value "text" --pretty
desktop-control invoke-element --window-id <hwnd> --name "Apply" --control-type button --pretty
desktop-control type-text --window-id <hwnd> --text "text to type" --pretty
desktop-control press-key --window-id <hwnd> --keys ctrl+a --keys backspace --pretty
desktop-control key --window-id <hwnd> --keys ctrl+a --keys backspace --pretty
desktop-control batch --file .tmp\batch-actions.json --pretty
desktop-control serve-stdio
desktop-control serve-pipe --name desktop-control
desktop-control pipe-request --name desktop-control --request-file .tmp\request.json --pretty
```

Each returned window includes `window_ref`. If an action reports a stale or missing window, recover explicitly with `recover-window` or JSON-RPC `recover_window`, refresh state, then retry only when the recovered target is unambiguous.

The stdio and named-pipe servers accept JSON-RPC methods `list_apps`, `launch_app`, `list_windows`, `observe`, `view`, `get_window`, `activate_window`, `get_window_state`, `state`, `screenshot`, `click`, `double_click`, `move`, `scroll`, `drag`, `type_text`, `type`, `key`, `press_key`, `keypress`, `find_elements`, `click_element`, `invoke_element`, `perform_secondary_action`, `set_element_value`, `set_value`, `wait`, `wait_window`, `wait_element`, `recover_window`, and `batch`.

For agent visual grounding, start with `observe` instead of manually listing windows and then calling `get-window-state`. `observe` selects a target by query/ref/id or the foreground window, captures a screenshot by default, can include UI Automation text, and returns the canonical window object and snapshot id for later actions.

Policy defaults are safe but configurable. Use `DESKTOP_CONTROL_BLOCKED_PROCESSES`, `DESKTOP_CONTROL_BLOCKED_TITLE_TERMS`, `DESKTOP_CONTROL_BLOCKED_CLASS_TERMS`, or `DESKTOP_CONTROL_POLICY_FILE` to add deployment-specific blocked targets without editing source. These settings add to the built-in hard denials; they do not remove terminal, credential, password-manager, security, or agent-host protections.

## Performance Rules

- Keep capture sessions and helper processes warm.
- Batch stable actions before verification.
- Use wait predicates instead of blind sleeps.
- Filter large UIA trees before sending them to the agent.
- Preserve original screenshot resolution for coordinate accuracy; if downscaling for model input, remap coordinates exactly.

## Output Rules

When giving an architecture answer, separate:

- Observed evidence.
- Inferred architecture.
- Recommended production design.
- Safety boundaries.
- Implementation phases.
- Test plan.

When implementing, end with concrete validation evidence and any untested platform assumptions.
