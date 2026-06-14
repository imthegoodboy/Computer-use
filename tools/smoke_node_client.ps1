$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlNodeClientTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\node-client-events.jsonl"
$readyPath = ".tmp\node-client-ready.txt"
$beforePath = ".tmp\node-client-before.png"
$afterPath = ".tmp\node-client-after.png"
$scriptPath = ".tmp\node-client-smoke.js"

Remove-Item -LiteralPath $logPath, $readyPath, $beforePath, $afterPath, $scriptPath -ErrorAction SilentlyContinue

$proc = Start-Process python -WorkingDirectory $repoRoot -ArgumentList @(
    "-u",
    "tools\mouse_target.py",
    "--title",
    $title,
    "--log",
    $logPath,
    "--ready",
    $readyPath
) -PassThru

$script = @'
const path = require("node:path");
const { createClient } = require(path.join(process.cwd(), "npm", "lib", "client.js"));

(async () => {
  const client = createClient({ timeoutMs: 20000 });
  try {
    const title = process.env.DESKTOP_CONTROL_SMOKE_TITLE;
    const beforePath = process.env.DESKTOP_CONTROL_SMOKE_BEFORE;
    const afterPath = process.env.DESKTOP_CONTROL_SMOKE_AFTER;
    await client.waitWindow({ query: title, timeout: 10, interval: 0.1 });
    const run = await client.agentRun({
      query: title,
      space: "client",
      observe: { out: beforePath },
      actions: [{ type: "click", x: 160, y: 150, button: "left" }],
      observe_after: { out: afterPath },
    });
    console.log(JSON.stringify({
      ok: run.ok,
      action: run.action,
      hwnd: run.current_observation.window.hwnd,
      before: run.observation.screenshots[0].path,
      after: run.next_observation.screenshots[0].path,
      trace: run.trace.map((item) => item.phase),
    }));
  } finally {
    client.close();
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
'@

try {
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue
    $env:DESKTOP_CONTROL_SMOKE_TITLE = $title
    $env:DESKTOP_CONTROL_SMOKE_BEFORE = $beforePath
    $env:DESKTOP_CONTROL_SMOKE_AFTER = $afterPath

    $script | Set-Content -LiteralPath $scriptPath -Encoding utf8
    $run = (& node $scriptPath) | ConvertFrom-Json
    if ($run.ok -ne $true) { throw "node client agent-run failed" }
    if ($run.action -ne "agent_run") { throw "node client action mismatch" }
    if (@($run.trace).Count -ne 3) { throw "node client trace length mismatch" }
    if (-not (Test-Path -LiteralPath $beforePath)) { throw "node client before screenshot missing" }
    if (-not (Test-Path -LiteralPath $afterPath)) { throw "node client after screenshot missing" }

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "node client click did not reach target" }
    if ([int]$press.x -ne 160 -or [int]$press.y -ne 150) {
        throw "node client click reached unexpected point $($press.x),$($press.y)"
    }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = [int]$run.hwnd
        before = [string]$run.before
        after = [string]$run.after
        click = @{ x = $press.x; y = $press.y; button = $press.button }
        trace = @($run.trace)
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 6
}
finally {
    Remove-Item Env:\DESKTOP_CONTROL_SMOKE_TITLE -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_SMOKE_BEFORE -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_SMOKE_AFTER -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $scriptPath -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
