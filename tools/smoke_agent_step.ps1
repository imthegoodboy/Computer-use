$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlAgentStepTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\agent-step-events.jsonl"
$readyPath = ".tmp\agent-step-ready.txt"
$screenshotPath = ".tmp\agent-step-observe.png"
$requestPath = ".tmp\agent-step-request.json"

Remove-Item -LiteralPath $logPath, $readyPath, $screenshotPath, $requestPath -ErrorAction SilentlyContinue

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

    $observed = (& node .\npm\bin\desktop-control.js observe --query $title --out $screenshotPath --pretty) | ConvertFrom-Json
    if ($observed.ok -ne $true) { throw "observe failed" }

    $request = [PSCustomObject]@{
        window = $observed.window
        space = "client"
        actions = @(
            [PSCustomObject]@{
                type = "click"
                x = 160
                y = 150
                button = "left"
            }
        )
    }
    $request | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $requestPath -Encoding utf8

    $step = (& node .\npm\bin\desktop-control.js agent-step --file $requestPath --pretty) | ConvertFrom-Json
    if ($step.ok -ne $true) { throw "agent-step failed" }
    if ($step.action -ne "agent_step") { throw "agent-step action mismatch" }
    if ($step.count -ne 1) { throw "agent-step count mismatch" }
    if ($step.batch.results[0].ok -ne $true) { throw "agent-step batch action failed" }
    if ($step.actions[0].params.expect_snapshot_id -ne $observed.window.snapshot_id) {
        throw "agent-step did not preserve snapshot guard"
    }

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "agent-step click did not reach target" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = [int]$observed.window.hwnd
        snapshotId = [string]$observed.window.snapshot_id
        click = @{ x = $press.x; y = $press.y; button = $press.button }
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
