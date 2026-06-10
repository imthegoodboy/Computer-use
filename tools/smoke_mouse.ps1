$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlMouseTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\mouse-events.jsonl"
$readyPath = ".tmp\mouse-ready.txt"
$screenshotPath = ".tmp\mouse-target.png"

Remove-Item -LiteralPath $logPath, $readyPath, $screenshotPath -ErrorAction SilentlyContinue

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
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path $readyPath)) {
        if ($proc.HasExited) {
            throw "Mouse target exited before it became ready. Exit code: $($proc.ExitCode)"
        }
        if ((Get-Date) -gt $deadline) {
            throw "Mouse target did not become ready."
        }
        Start-Sleep -Milliseconds 100
    }

    $env:PYTHONPATH = "src"

    $windowsRaw = python -m desktop_control list-windows --query $title
    $windowsData = $windowsRaw | ConvertFrom-Json
    if (-not $windowsData.windows -or $windowsData.windows.Count -eq 0) {
        throw "Mouse target window was not discovered."
    }

    $hwnd = [int]$windowsData.windows[0].hwnd

    $state = (python -m desktop_control state --window-id $hwnd --screenshot $screenshotPath) | ConvertFrom-Json
    $move = (python -m desktop_control move --window-id $hwnd --space client --x 140 --y 130) | ConvertFrom-Json
    Start-Sleep -Milliseconds 150
    $click = (python -m desktop_control click --window-id $hwnd --space client --x 160 --y 150) | ConvertFrom-Json
    Start-Sleep -Milliseconds 150
    $drag = (python -m desktop_control drag --window-id $hwnd --space client --from-x 180 --from-y 180 --to-x 360 --to-y 260 --duration 0.25 --steps 16) | ConvertFrom-Json
    Start-Sleep -Milliseconds 150
    $scroll = (python -m desktop_control scroll --window-id $hwnd --space client --x 220 --y 220 --delta -2) | ConvertFrom-Json
    Start-Sleep -Milliseconds 350

    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }

    $types = @($events | ForEach-Object { $_.type })
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    $release = @($events | Where-Object { $_.type -eq "button_release" }) | Select-Object -First 1
    $dragMotionCount = @($events | Where-Object { $_.type -eq "drag_motion" }).Count
    $wheelCount = @($events | Where-Object { $_.type -like "mouse_wheel*" }).Count

    if ($state.ok -ne $true) { throw "state failed" }
    if ($move.ok -ne $true) { throw "move failed" }
    if ($click.ok -ne $true) { throw "click failed" }
    if ($drag.ok -ne $true) { throw "drag failed" }
    if ($scroll.ok -ne $true) { throw "scroll failed" }
    if (-not (Test-Path $screenshotPath)) { throw "screenshot was not created" }
    if (-not ($types -contains "motion")) { throw "motion event was not recorded" }
    if (-not ($types -contains "button_press")) { throw "button_press event was not recorded" }
    if (-not ($types -contains "button_release")) { throw "button_release event was not recorded" }
    if ($dragMotionCount -lt 1) { throw "drag_motion event was not recorded" }
    if ($wheelCount -lt 1) { throw "mouse wheel event was not recorded" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        eventCount = $events.Count
        dragMotionCount = $dragMotionCount
        wheelCount = $wheelCount
        firstPress = if ($press) { @{ x = $press.x; y = $press.y; button = $press.button } } else { $null }
        firstRelease = if ($release) { @{ x = $release.x; y = $release.y; button = $release.button } } else { $null }
        screenshotBytes = (Get-Item $screenshotPath).Length
        clientRect = $state.window.client_rect
    } | ConvertTo-Json -Depth 6
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
