$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlRecoveryTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$firstLogPath = ".tmp\recovery-events-first.jsonl"
$secondLogPath = ".tmp\recovery-events-second.jsonl"
$firstReadyPath = ".tmp\recovery-ready-first.txt"
$secondReadyPath = ".tmp\recovery-ready-second.txt"
$refPath = ".tmp\recovery-window-ref.json"

Remove-Item -LiteralPath $firstLogPath, $secondLogPath, $firstReadyPath, $secondReadyPath, $refPath -ErrorAction SilentlyContinue

function Start-RecoveryTarget($logPath, $readyPath) {
    Start-Process python -WorkingDirectory $repoRoot -ArgumentList @(
        "-u",
        "tools\mouse_target.py",
        "--title",
        $title,
        "--log",
        $logPath,
        "--ready",
        $readyPath
    ) -PassThru
}

$firstProc = $null
$secondProc = $null

try {
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue
    $env:PYTHONPATH = "src"

    $firstProc = Start-RecoveryTarget $firstLogPath $firstReadyPath
    $firstWindow = (python -m desktop_control wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($firstWindow.ok -ne $true) { throw "first wait-window failed" }
    $firstHwnd = [int]$firstWindow.window.hwnd
    $firstWindow.window.window_ref | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $refPath -Encoding utf8

    Stop-Process -Id $firstProc.Id -Force
    $firstProc.WaitForExit(3000) | Out-Null

    $secondProc = Start-RecoveryTarget $secondLogPath $secondReadyPath
    $secondWindow = (python -m desktop_control wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($secondWindow.ok -ne $true) { throw "second wait-window failed" }

    $recovered = (python -m desktop_control recover-window --ref-file $refPath) | ConvertFrom-Json
    if ($recovered.ok -ne $true) { throw "recover-window failed" }
    if ($recovered.window.title -ne $title) { throw "recovered wrong title" }

    $recoveredHwnd = [int]$recovered.window.hwnd
    python -m desktop_control click --window-id $recoveredHwnd --space client --x 160 --y 150 | Out-Null

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $secondLogPath) {
        $events = Get-Content -LiteralPath $secondLogPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "recovered click did not reach relaunched target" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        firstHwnd = $firstHwnd
        recoveredHwnd = $recoveredHwnd
        secondHwnd = [int]$secondWindow.window.hwnd
        click = @{ x = $press.x; y = $press.y; button = $press.button }
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($firstProc -and -not $firstProc.HasExited) {
        Stop-Process -Id $firstProc.Id -Force
    }
    if ($secondProc -and -not $secondProc.HasExited) {
        Stop-Process -Id $secondProc.Id -Force
    }
}
