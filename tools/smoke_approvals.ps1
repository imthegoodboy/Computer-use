$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlApprovalTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\approval-events.jsonl"
$readyPath = ".tmp\approval-ready.txt"
$approvalPath = ".tmp\desktop-control-approvals-smoke.json"
$deniedStdoutPath = ".tmp\approval-denied.out"
$deniedStderrPath = ".tmp\approval-denied.err"

Remove-Item -LiteralPath $logPath, $readyPath, $approvalPath, $deniedStdoutPath, $deniedStderrPath -ErrorAction SilentlyContinue

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
    $env:PYTHONPATH = "src"
    $env:DESKTOP_CONTROL_REQUIRE_APPROVALS = "1"
    $env:DESKTOP_CONTROL_APPROVALS_FILE = $approvalPath

    $windowResult = (python -m desktop_control wait-window --query $title --timeout 10 --interval 0.1) | ConvertFrom-Json
    if ($windowResult.ok -ne $true) { throw "wait-window failed" }
    $hwnd = [int]$windowResult.window.hwnd

    $deniedProc = Start-Process python -WorkingDirectory $repoRoot -ArgumentList @(
        "-m",
        "desktop_control",
        "click",
        "--window-id",
        "$hwnd",
        "--space",
        "client",
        "--x",
        "160",
        "--y",
        "150"
    ) -RedirectStandardOutput $deniedStdoutPath -RedirectStandardError $deniedStderrPath -Wait -PassThru
    if ($deniedProc.ExitCode -eq 0) {
        throw "unapproved click unexpectedly succeeded"
    }
    $deniedJson = ((Get-Content -LiteralPath $deniedStderrPath -Raw -ErrorAction SilentlyContinue) +
        (Get-Content -LiteralPath $deniedStdoutPath -Raw -ErrorAction SilentlyContinue))
    $denied = $deniedJson | ConvertFrom-Json
    if ($denied.ok -ne $false -or $denied.error.code -ne "approval_required") {
        throw "unapproved click did not fail with approval_required"
    }

    $approval = (python -m desktop_control approve-window --window-id $hwnd) | ConvertFrom-Json
    if ($approval.ok -ne $true) { throw "approve-window failed" }

    $click = (python -m desktop_control click --window-id $hwnd --space client --x 160 --y 150) | ConvertFrom-Json
    if ($click.ok -ne $true) { throw "approved click failed" }

    Start-Sleep -Milliseconds 250
    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }
    $press = @($events | Where-Object { $_.type -eq "button_press" }) | Select-Object -First 1
    if (-not $press) { throw "approved click did not reach target" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        deniedCode = $denied.error.code
        approvalFile = $approval.approval_file
        firstPress = @{ x = $press.x; y = $press.y; button = $press.button }
    } | ConvertTo-Json -Depth 5
}
finally {
    Remove-Item Env:\DESKTOP_CONTROL_REQUIRE_APPROVALS -ErrorAction SilentlyContinue
    Remove-Item Env:\DESKTOP_CONTROL_APPROVALS_FILE -ErrorAction SilentlyContinue
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
