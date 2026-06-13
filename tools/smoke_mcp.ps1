$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:PYTHONPATH = "src"

$requests = @(
    @{
        jsonrpc = "2.0"
        id = 1
        method = "initialize"
        params = @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{ name = "desktop-control-smoke"; version = "0" }
        }
    },
    @{
        jsonrpc = "2.0"
        method = "notifications/initialized"
        params = @{}
    },
    @{
        jsonrpc = "2.0"
        id = 2
        method = "tools/list"
        params = @{}
    },
    @{
        jsonrpc = "2.0"
        id = 3
        method = "tools/call"
        params = @{
            name = "list_windows"
            arguments = @{ query = "unlikely-mcp-smoke-window" }
        }
    }
)

$inputLines = ($requests | ForEach-Object { $_ | ConvertTo-Json -Depth 12 -Compress }) -join "`n"
$rawOutput = $inputLines | python -m desktop_control serve-mcp
$rawLines = @($rawOutput | Where-Object { $_.Trim() })
$responses = @(
    $rawLines |
        ForEach-Object { $_ | ConvertFrom-Json }
)

if ($responses.Count -ne 3) { throw "Expected 3 MCP responses, got $($responses.Count)" }
$capabilitiesJson = $responses[0].result.capabilities | ConvertTo-Json -Depth 8 -Compress
if ($capabilitiesJson -notmatch '"tools"') { throw "initialize did not declare tools" }
if ($capabilitiesJson -notmatch '"listChanged":false') { throw "initialize tools capability was malformed" }

$toolNames = @($responses[1].result.tools | ForEach-Object { $_.name })
foreach ($requiredTool in @("list_windows", "get_window_state", "press_key", "batch")) {
    if ($toolNames -notcontains $requiredTool) { throw "MCP tools/list missing $requiredTool" }
}

if ($responses[2].result.isError -ne $false) { throw "MCP list_windows call returned tool error" }
if ($responses[2].result.structuredContent.ok -ne $true) { throw "MCP list_windows structured content not ok" }

[PSCustomObject]@{
    ok = $true
    toolCount = $toolNames.Count
    callTool = "list_windows"
    windowCount = @($responses[2].result.structuredContent.windows).Count
} | ConvertTo-Json -Depth 5
