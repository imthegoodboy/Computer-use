$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlSnapshotTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\snapshot-events.jsonl"
$readyPath = ".tmp\snapshot-ready.txt"
$staleStdoutPath = ".tmp\snapshot-stale.out"
$staleStderrPath = ".tmp\snapshot-stale.err"

Remove-Item -LiteralPath $logPath, $readyPath, $staleStdoutPath, $staleStderrPath -ErrorAction SilentlyContinue

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
    if (-not $snapshotId) { throw "state did not include snapshot_id" }

    $goodClick = (python -m desktop_control click --window-id $hwnd --space client --x 160 --y 150 --expect-snapshot-id $snapshotId) | ConvertFrom-Json
    if ($goodClick.ok -ne $true) { throw "click with matching snapshot failed" }

    $staleProc = Start-Process python -WorkingDirectory $repoRoot -ArgumentList @(
        "-m",
        "desktop_control",
        "click",
        "--window-id",
        "$hwnd",
        "--space",
        "client",
        "--x",
        "180",
        "--y",
        "180",
        "--expect-snapshot-id",
        "not-the-current-snapshot"
    ) -RedirectStandardOutput $staleStdoutPath -RedirectStandardError $staleStderrPath -Wait -PassThru
    if ($staleProc.ExitCode -eq 0) {
        throw "click with stale snapshot unexpectedly succeeded"
    }
    $staleJson = ((Get-Content -LiteralPath $staleStderrPath -Raw -ErrorAction SilentlyContinue) +
        (Get-Content -LiteralPath $staleStdoutPath -Raw -ErrorAction SilentlyContinue))
    $stale = $staleJson | ConvertFrom-Json
    if ($stale.error.code -ne "stale_snapshot") { throw "stale click returned $($stale.error.code)" }

    Start-Sleep -Milliseconds 250
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $presses = @($events | Where-Object { $_.type -eq "button_press" })
    if ($presses.Count -ne 1) { throw "expected exactly one click to reach target, got $($presses.Count)" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        snapshotId = $snapshotId
        acceptedClick = @{ x = $presses[0].x; y = $presses[0].y; button = $presses[0].button }
        rejectedCode = $stale.error.code
        reachedTargetClicks = $presses.Count
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
