$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlAgentRunTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\agent-run-events.jsonl"
$readyPath = ".tmp\agent-run-ready.txt"
$beforePath = ".tmp\agent-run-before.png"
$afterPath = ".tmp\agent-run-after.png"
$requestPath = ".tmp\agent-run-request.json"

Remove-Item -LiteralPath $logPath, $readyPath, $beforePath, $afterPath, $requestPath -ErrorAction SilentlyContinue

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

try {
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue

    $windowResult = (& node .\npm\bin\desktop-control.js wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($windowResult.ok -ne $true) { throw "wait-window failed" }

    $request = [PSCustomObject]@{
        query = $title
        space = "client"
        observe = [PSCustomObject]@{
            out = $beforePath
        }
        actions = @(
            [PSCustomObject]@{
                type = "click"
                x = 160
                y = 150
                button = "left"
            }
        )
        observe_after = [PSCustomObject]@{
            out = $afterPath
        }
    }
    $request | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $requestPath -Encoding utf8

    $run = (& node .\npm\bin\desktop-control.js agent-run --file $requestPath --pretty) | ConvertFrom-Json
    if ($run.ok -ne $true) { throw "agent-run failed" }
    if ($run.action -ne "agent_run") { throw "agent-run action mismatch" }
    if ($run.step.action -ne "agent_step") { throw "agent-run step mismatch" }
    if ($run.step.batch.results[0].ok -ne $true) { throw "agent-run batch action failed" }
    if (-not $run.observation.screenshots[0].path) { throw "agent-run missing initial screenshot" }
    if (-not $run.next_observation.screenshots[0].path) { throw "agent-run missing next screenshot" }
    if ($run.current_observation.generation -ne $run.next_observation.generation) {
        throw "agent-run current observation was not updated"
    }
    if ([int]$run.step.actions[0].params.window.hwnd -ne [int]$run.observation.window.hwnd) {
        throw "agent-run did not inject observed window context"
    }
    if (@($run.trace).Count -ne 3) { throw "agent-run trace length mismatch" }

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "agent-run click did not reach target" }
    if ([int]$press.x -ne 160 -or [int]$press.y -ne 150) {
        throw "agent-run click reached unexpected point $($press.x),$($press.y)"
    }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = [int]$run.current_observation.window.hwnd
        snapshotId = [string]$run.current_observation.window.snapshot_id
        before = [string]$run.observation.screenshots[0].path
        after = [string]$run.next_observation.screenshots[0].path
        click = @{ x = $press.x; y = $press.y; button = $press.button }
        trace = @($run.trace | ForEach-Object { $_.phase })
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
