$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlObserveTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\observe-events.jsonl"
$readyPath = ".tmp\observe-ready.txt"
$screenshotPath = ".tmp\observe.png"

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
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue

    $windowResult = (& node .\npm\bin\desktop-control.js wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($windowResult.ok -ne $true) { throw "wait-window failed" }

    $observed = (& node .\npm\bin\desktop-control.js observe --query $title --out $screenshotPath --inline-screenshot --pretty) | ConvertFrom-Json
    if ($observed.ok -ne $true) { throw "observe failed" }
    if ($observed.action -ne "observe") { throw "observe action mismatch" }
    if ($observed.selection.source -ne "query") { throw "observe selection source mismatch" }
    if ($observed.selection.match_count -ne 1) { throw "observe did not select exactly one window" }
    if ([int]$observed.window.hwnd -ne [int]$windowResult.window.hwnd) { throw "observe selected the wrong window" }
    if ([string]::IsNullOrWhiteSpace($observed.window.snapshot_id)) { throw "observe missing window snapshot_id" }

    $screenshots = @($observed.screenshots)
    if ($screenshots.Count -ne 1) { throw "observe did not return exactly one screenshot" }
    $image = $screenshots[0].image
    if (-not (Test-Path -LiteralPath $screenshotPath)) { throw "observe screenshot was not written" }
    if ($image.bytes -le 0) { throw "observe screenshot had no bytes" }
    if ($image.nonblank -ne $true) { throw "observe screenshot was blank" }
    if ($image.unique_sample_colors -lt 2) { throw "observe screenshot had too few colors" }
    if ([string]::IsNullOrWhiteSpace($image.sha256)) { throw "observe screenshot missing sha256" }
    if ($screenshots[0].mime_type -ne "image/png") { throw "observe screenshot missing image/png MIME type" }
    if (-not ([string]$screenshots[0].url).StartsWith("data:image/png;base64,")) {
        throw "observe screenshot missing inline data URL"
    }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = [int]$observed.window.hwnd
        snapshotId = [string]$observed.window.snapshot_id
        screenshot = $screenshots[0].path
        bytes = [int]$image.bytes
        uniqueSampleColors = [int]$image.unique_sample_colors
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
