param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$Orchestrator = Join-Path $FoundryRoot "orchestrator\arkaon-orchestrator.py"
$StartupState = Join-Path $FoundryRoot "state\startup-last-run.json"

if (-not (Test-Path -LiteralPath $Orchestrator)) {
    throw "Central orchestrator entrypoint not found: $Orchestrator"
}

$startedAt = [DateTime]::UtcNow.ToString("o")
Write-Output "ARKAON central orchestrator starting at $startedAt"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Python launcher not found. Install Python 3.11+ and retry."
}

& $python.Source (Resolve-Path -LiteralPath $Orchestrator).Path
if ($LASTEXITCODE -ne 0) {
    throw "Central orchestrator failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $StartupState) | Out-Null
@{
    schema_version = "apf.orchestrator-startup.v1"
    observed_at = $startedAt
    foundry_root = $FoundryRoot
    source = "WINDOWS_LOGON_OR_MANUAL"
    machine_identifier_collected = $false
    automatic_learning = $false
    production_change_allowed = $false
} | ConvertTo-Json | Set-Content -LiteralPath $StartupState -Encoding UTF8

Write-Output "ARKAON central orchestrator completed. Review inbox\eternian-review before any change."
