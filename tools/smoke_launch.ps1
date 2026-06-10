$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlLaunchTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\launch-events.jsonl"
$readyPath = ".tmp\launch-ready.txt"
$pythonExe = (Get-Command python).Source

Remove-Item -LiteralPath $logPath, $readyPath -ErrorAction SilentlyContinue

$windowPid = $null

try {
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue
    $env:PYTHONPATH = "src"

    $launch = (python -m desktop_control launch-app `
        --app $pythonExe `
        --arg=-u `
        --arg=tools\mouse_target.py `
        --arg=--title `
        --arg=$title `
        --arg=--log `
        --arg=$logPath `
        --arg=--ready `
        --arg=$readyPath `
        --cwd $repoRoot `
        --wait-query $title `
        --timeout 10 `
        --interval 0.1) | ConvertFrom-Json

    if ($launch.ok -ne $true) { throw "launch-app failed" }
    $hwnd = [int]$launch.window.hwnd
    $windowPid = [int]$launch.window.process_id

    $apps = (python -m desktop_control list-apps --query python --no-start-menu --limit 20) | ConvertFrom-Json
    $runningPython = @($apps.apps | Where-Object { $_.running -eq $true -and $_.process_ids -contains $windowPid }) | Select-Object -First 1
    if (-not $runningPython) { throw "list-apps did not report launched python window" }

    python -m desktop_control click --window-id $hwnd --space client --x 160 --y 150 | Out-Null

    Start-Sleep -Milliseconds 350
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "click did not reach launched target" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        processId = $windowPid
        launchedApp = $launch.app.display_name
        listedApp = $runningPython.display_name
        click = @{ x = $press.x; y = $press.y; button = $press.button }
        eventCount = @($events).Count
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($windowPid) {
        Stop-Process -Id $windowPid -Force -ErrorAction SilentlyContinue
    }
}
