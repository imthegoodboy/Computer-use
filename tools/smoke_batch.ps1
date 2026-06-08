$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlBatchTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\batch-events.jsonl"
$readyPath = ".tmp\batch-ready.txt"
$batchPath = ".tmp\batch-actions.json"

Remove-Item -LiteralPath $logPath, $readyPath, $batchPath -ErrorAction SilentlyContinue

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
    $env:PYTHONPATH = "src"

    $windowResult = (python -m desktop_control wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($windowResult.ok -ne $true) { throw "wait-window failed" }
    $hwnd = [int]$windowResult.window.hwnd
    $state = (python -m desktop_control state --window-id $hwnd) | ConvertFrom-Json
    $snapshotId = [string]$state.window.snapshot_id

    $batch = @{
        actions = @(
            @{ method = "move"; params = @{ window_id = $hwnd; space = "client"; x = 140; y = 130; expect_snapshot_id = $snapshotId } },
            @{ method = "click"; params = @{ window_id = $hwnd; space = "client"; x = 160; y = 150; expect_snapshot_id = $snapshotId } },
            @{ method = "drag"; params = @{ window_id = $hwnd; space = "client"; from_x = 180; from_y = 180; to_x = 360; to_y = 260; duration = 0.25; steps = 16; expect_snapshot_id = $snapshotId } },
            @{ method = "scroll"; params = @{ window_id = $hwnd; space = "client"; x = 220; y = 220; delta = -2; expect_snapshot_id = $snapshotId } }
        )
    }
    $batch | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $batchPath -Encoding utf8

    $batchResult = (python -m desktop_control batch --file $batchPath) | ConvertFrom-Json
    if ($batchResult.ok -ne $true -or $batchResult.count -ne 4) { throw "batch execution failed" }

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    $dragMotionCount = @($events | Where-Object { $_.type -eq "drag_motion" }).Count
    $wheelCount = @($events | Where-Object { $_.type -eq "mouse_wheel" }).Count

    if (-not $press) { throw "batched click did not reach target" }
    if ($dragMotionCount -lt 1) { throw "batched drag did not produce drag motion" }
    if ($wheelCount -lt 1) { throw "batched scroll did not produce wheel event" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        batchCount = $batchResult.count
        firstPress = @{ x = $press.x; y = $press.y; button = $press.button }
        dragMotionCount = $dragMotionCount
        wheelCount = $wheelCount
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
