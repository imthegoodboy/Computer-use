$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$title = "DesktopControlUiaTarget-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$logPath = ".tmp\uia-events.jsonl"
$readyPath = ".tmp\uia-ready.txt"
$value = "uia smoke " + [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")

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
    $deadline = (Get-Date).AddSeconds(10)
    while (-not (Test-Path $readyPath)) {
        if ($proc.HasExited) {
            throw "UIA target exited before it became ready. Exit code: $($proc.ExitCode)"
        }
        if ((Get-Date) -gt $deadline) {
            throw "UIA target did not become ready."
        }
        Start-Sleep -Milliseconds 100
    }

    $env:PYTHONPATH = "src"
    $windowsRaw = python -m desktop_control list-windows --query $title
    $windowsData = $windowsRaw | ConvertFrom-Json
    if (-not $windowsData.windows -or $windowsData.windows.Count -eq 0) {
        throw "UIA target window was not discovered."
    }
    $hwnd = [int]$windowsData.windows[0].hwnd

    $editElements = (python -m desktop_control find-elements --window-id $hwnd --control-type edit) | ConvertFrom-Json
    $buttonElements = (python -m desktop_control find-elements --window-id $hwnd --name Apply --control-type button) | ConvertFrom-Json
    $setResult = (python -m desktop_control set-element-value --window-id $hwnd --control-type edit --value $value) | ConvertFrom-Json
    $invokeResult = (python -m desktop_control invoke-element --window-id $hwnd --name Apply --control-type button) | ConvertFrom-Json
    Start-Sleep -Milliseconds 350

    $events = @()
    if (Test-Path $logPath) {
        $events = Get-Content -LiteralPath $logPath -Encoding utf8 |
            Where-Object { $_.Trim() } |
            ForEach-Object { $_ | ConvertFrom-Json }
    }

    $buttonEvent = @($events | Where-Object { $_.type -eq "button_invoked" }) | Select-Object -Last 1

    if ($editElements.ok -ne $true -or $editElements.elements.Count -lt 1) { throw "edit element was not found" }
    if ($buttonElements.ok -ne $true -or $buttonElements.elements.Count -lt 1) { throw "button element was not found" }
    if ($setResult.ok -ne $true) { throw "set-element-value failed" }
    if ($invokeResult.ok -ne $true) { throw "invoke-element failed" }
    if (-not $buttonEvent) { throw "button invocation was not recorded" }
    if ($buttonEvent.text -ne $value) { throw "button invocation saw wrong edit value: $($buttonEvent.text)" }

    [PSCustomObject]@{
        ok = $true
        title = $title
        hwnd = $hwnd
        editMatches = $editElements.elements.Count
        buttonMatches = $buttonElements.elements.Count
        setMethod = $setResult.method
        invokeMethod = $invokeResult.method
        invokedText = $buttonEvent.text
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force
    }
}
