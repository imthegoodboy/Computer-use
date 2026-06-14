Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $RepoRoot
try {
    $versionOutput = node .\npm\bin\desktop-control.js --version
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control --version exited with $LASTEXITCODE"
    }
    if ($versionOutput -notmatch "desktop-control 0\.1\.0") {
        throw "Unexpected version output: $versionOutput"
    }

    $doctorOutput = node .\npm\bin\desktop-control.js --npm-wrapper-doctor
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control --npm-wrapper-doctor exited with $LASTEXITCODE"
    }
    $doctor = $doctorOutput | ConvertFrom-Json
    if (-not $doctor.ok) {
        throw "Wrapper doctor failed: $($doctorOutput -join [Environment]::NewLine)"
    }

    $listOutput = node .\npm\bin\desktop-control.js list-windows --query "unlikely-npm-smoke-window" --pretty
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control list-windows exited with $LASTEXITCODE"
    }
    $payload = $listOutput | ConvertFrom-Json
    if (-not $payload.ok) {
        throw "list-windows payload was not ok"
    }
    if ($null -eq $payload.windows) {
        throw "list-windows payload did not include windows"
    }

    $observeHelp = node .\npm\bin\desktop-control.js observe --help
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control observe --help exited with $LASTEXITCODE"
    }
    $observeHelpText = $observeHelp -join [Environment]::NewLine
    if ($observeHelpText -notmatch "--query" -or $observeHelpText -notmatch "--inline-screenshot") {
        throw "observe help did not include expected visual options"
    }

    $agentStepHelp = node .\npm\bin\desktop-control.js agent-step --help
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control agent-step --help exited with $LASTEXITCODE"
    }
    $agentStepHelpText = $agentStepHelp -join [Environment]::NewLine
    if ($agentStepHelpText -notmatch "agent-step" -or $agentStepHelpText -notmatch "--file") {
        throw "agent-step help did not expose the expected command/options"
    }

    $agentRunHelp = node .\npm\bin\desktop-control.js agent-run --help
    if ($LASTEXITCODE -ne 0) {
        throw "desktop-control agent-run --help exited with $LASTEXITCODE"
    }
    $agentRunHelpText = $agentRunHelp -join [Environment]::NewLine
    if ($agentRunHelpText -notmatch "agent-run" -or $agentRunHelpText -notmatch "--no-observe-after" -or $agentRunHelpText -notmatch "--inline-screenshot") {
        throw "agent-run help did not expose the expected command/options"
    }

    "npm CLI smoke passed"
}
finally {
    Pop-Location
}
