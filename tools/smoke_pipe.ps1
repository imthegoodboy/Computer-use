$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null

$pipeName = "desktop-control-smoke-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
$requestPath = ".tmp\pipe-request.json"
$secondRequestPath = ".tmp\pipe-request-second.json"
$serverOut = ".tmp\pipe-server.out.log"
$serverErr = ".tmp\pipe-server.err.log"

Remove-Item -LiteralPath $requestPath, $secondRequestPath, $serverOut, $serverErr -ErrorAction SilentlyContinue

$server = $null

try {
    $env:PYTHONPATH = "src"
    $server = Start-Process python -WindowStyle Hidden -WorkingDirectory $repoRoot -ArgumentList @(
        "-m",
        "desktop_control",
        "serve-pipe",
        "--name",
        $pipeName
    ) -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru

    @{
        jsonrpc = "2.0"
        id = 1
        method = "list_windows"
        params = @{ query = "unlikely-pipe-smoke-window" }
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $requestPath -Encoding utf8

    $response = $null
    $deadline = (Get-Date).AddSeconds(10)
    do {
        try {
            $response = (python -m desktop_control pipe-request --name $pipeName --request-file $requestPath --timeout 1) | ConvertFrom-Json
            break
        }
        catch {
            if ((Get-Date) -ge $deadline) {
                throw
            }
            Start-Sleep -Milliseconds 100
        }
    } while ($true)

    if ($response.jsonrpc -ne "2.0") { throw "invalid JSON-RPC response" }
    if ($response.id -ne 1) { throw "response id mismatch" }
    if ($response.result.ok -ne $true) { throw "pipe list_windows did not return ok" }

    @{
        jsonrpc = "2.0"
        id = 2
        method = "list_apps"
        params = @{ query = "unlikely-pipe-smoke-app"; include_start_menu = $false; include_windows = $false }
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $secondRequestPath -Encoding utf8

    $secondResponse = (python -m desktop_control pipe-request --name $pipeName --request-file $secondRequestPath --timeout 3) | ConvertFrom-Json
    if ($secondResponse.jsonrpc -ne "2.0") { throw "invalid second JSON-RPC response" }
    if ($secondResponse.id -ne 2) { throw "second response id mismatch" }
    if ($secondResponse.result.ok -ne $true) { throw "pipe list_apps did not return ok" }

    Start-Sleep -Milliseconds 200
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
    }

    [PSCustomObject]@{
        ok = $true
        pipeName = $pipeName
        responseId = $response.id
        secondResponseId = $secondResponse.id
        windowCount = @($response.result.windows).Count
        appCount = @($secondResponse.result.apps).Count
        serverExitCode = if ($server.HasExited) { $server.ExitCode } else { $null }
    } | ConvertTo-Json -Depth 5
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force
    }
}
