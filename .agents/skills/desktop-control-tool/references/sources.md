# Desktop Control Tool Sources

## Scope Boundary

This research reconstructs architecture from exposed local skill files, wrapper code, package type definitions, plugin metadata, and public documentation. It does not depend on decompiling proprietary binaries, bypassing Codex controls, or disabling operating-system security boundaries.

## Local Evidence

- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\skills\computer-use\SKILL.md`
  - Public skill instructions for Codex Computer Use.
  - Establishes the exposed tool API, safety rules, state handling, and action workflow.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\scripts\computer-use-client.mjs`
  - Exposed JavaScript client wrapper.
  - Shows the native-pipe transport, length-prefixed JSON-RPC framing, request/response flow, and approval callback path.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\.codex-plugin\plugin.json`
  - Plugin manifest.
  - Confirms Windows desktop-control intent, interactive/read/write capability class, and user approval/stop-control framing.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\node_modules\@oai\sky\package.json`
  - Local package metadata for the exposed Computer Use client package.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\node_modules\@oai\sky\types\window2`
  - Type definitions for the exposed Window2 tool surface.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\node_modules\@oai\sky\targets\windows\internal\computer_use_client_base.d.ts`
  - Type definition showing the Windows client base shape and transport boundary.
- `C:\Users\parth\.codex\plugins\cache\openai-bundled\computer-use\26.602.40724\node_modules\@oai\sky\targets\windows\internal\codex_turn_metadata.js`
  - Exposed metadata bridge for Codex turn metadata and app approval data.

## Public OpenAI Docs

- Codex Computer Use: https://developers.openai.com/codex/app/computer-use
  - Confirms desktop GUI operation, app approval, safety prompts, and Windows active-desktop behavior.
- OpenAI API Computer Use guide: https://developers.openai.com/api/docs/guides/tools-computer-use
  - Confirms the computer-call loop, screenshot feedback cycle, action names, batching, and action-result verification pattern.
- OpenAI deployment checklist, built-in tools: https://developers.openai.com/api/docs/guides/deployment-checklist#leverage-built-in-tools
  - Supports preserving familiar built-in tool shapes when creating custom tools.

## Windows API Docs

- `SendInput`: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
  - Confirms synthesized keyboard and mouse input, serial insertion into the input stream, and UIPI integrity-level limits.
- UI Automation overview: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview
  - Confirms the programmatic accessibility tree, UI elements, properties, and control patterns.
- `GraphicsCaptureItem`: https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.graphicscaptureitem
  - Confirms Windows Graphics Capture target representation.
- `IGraphicsCaptureItemInterop::CreateForWindow`: https://learn.microsoft.com/en-sg/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow
  - Confirms HWND-to-capture-item creation for window capture.
- `Direct3D11CaptureFramePool`: https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframepool
  - Confirms frame-pool capture behavior and free-threaded frame-pool support.
- `SetForegroundWindow`: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
  - Confirms foreground-window activation constraints.

## Comparable Agent Architecture

- Microsoft UFO2: https://www.microsoft.com/en-us/research/publication/ufo2-the-desktop-agentos/
  - Supports the architecture pattern of layered desktop-agent components and desktop automation services.
- UFO2 overview docs: https://github.com/microsoft/UFO/blob/main/documents/docs/ufo2/overview.md
  - Shows how a desktop-agent OS can decompose perception, control, and workflow orchestration.
- Microsoft OmniParser: https://www.microsoft.com/en-us/research/articles/omniparser-for-pure-vision-based-gui-agent/
  - Supports the recommendation to use vision parsing as a fallback when structured UI metadata is weak.
