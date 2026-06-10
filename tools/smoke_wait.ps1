$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlWaitTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\wait-events.jsonl"
$readyPath = ".tmp\wait-ready.txt"

Remove-Item -LiteralPath $logPath, $readyPath -ErrorAction SilentlyContinue

$proc = Start-Process python -WorkingDirectory $repoRoot -ArgumentList @(
    "-u",
    "tools\uia_target.py",
    "--title",
    $title,
    "--log",
    $logPath,
    "--ready",
    $readyPath
) -PassThru

try {
    $env:PYTHONPATH = "src"
    $windowResult = (python -m desktop_control wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($windowResult.ok -ne $true) { throw "wait-window failed" }
    $hwnd = [int]$windowResult.window.hwnd

    $elementResult = (python -m desktop_control wait-element --window-id $hwnd --name Apply --control-type button --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($elementResult.ok -ne $true) { throw "wait-element failed" }
    if ($elementResult.element.name -ne "Apply") { throw "wait-element matched wrong element" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        windowAttempts = $windowResult.attempts
        elementAttempts = $elementResult.attempts
        elementName = $elementResult.element.name
        elementControlType = $elementResult.element.control_type
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
