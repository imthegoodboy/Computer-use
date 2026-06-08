$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlCaptureTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\capture-events.jsonl"
$readyPath = ".tmp\capture-ready.txt"
$autoPath = ".tmp\capture-auto.png"
$pilPath = ".tmp\capture-pil.png"
$mssPath = ".tmp\capture-mss.png"

Remove-Item -LiteralPath $logPath, $readyPath, $autoPath, $pilPath, $mssPath -ErrorAction SilentlyContinue

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
    $snapshotId = [string]$windowResult.window.snapshot_id

    $auto = (python -m desktop_control screenshot --window-id $hwnd --out $autoPath --backend auto) | ConvertFrom-Json
    $pil = (python -m desktop_control screenshot --window-id $hwnd --out $pilPath --backend pil) | ConvertFrom-Json
    $mss = (python -m desktop_control screenshot --window-id $hwnd --out $mssPath --backend mss) | ConvertFrom-Json

    foreach ($capture in @($auto, $pil, $mss)) {
        if ($capture.ok -ne $true) { throw "screenshot command failed" }
        if ($capture.screenshot.width -ne $windowResult.window.rect.width) { throw "screenshot width did not match window width" }
        if ($capture.screenshot.height -ne $windowResult.window.rect.height) { throw "screenshot height did not match window height" }
        if ($capture.screenshot.window_snapshot_id -ne $snapshotId) { throw "screenshot snapshot id did not match window state" }
        if ($capture.screenshot.image.bytes -le 0) { throw "screenshot had no bytes" }
        if ($capture.screenshot.image.nonblank -ne $true) { throw "screenshot was blank" }
        if ($capture.screenshot.image.unique_sample_colors -lt 2) { throw "screenshot had too few colors" }
        if ([string]::IsNullOrWhiteSpace($capture.screenshot.image.sha256)) { throw "screenshot missing sha256" }
    }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        snapshotId = $snapshotId
        autoBackend = $auto.screenshot.backend
        pilBackend = $pil.screenshot.backend
        mssBackend = $mss.screenshot.backend
        autoBytes = $auto.screenshot.image.bytes
        pilBytes = $pil.screenshot.image.bytes
        mssBytes = $mss.screenshot.image.bytes
        autoUniqueColors = $auto.screenshot.image.unique_sample_colors
        pilUniqueColors = $pil.screenshot.image.unique_sample_colors
        mssUniqueColors = $mss.screenshot.image.unique_sample_colors
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
