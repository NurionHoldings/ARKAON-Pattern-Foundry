param(
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [int]$WatchSeconds = 15
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $FoundryRoot

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required."
}
gh auth status | Out-Null

$Python = Join-Path $FoundryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

$env:PYTHONPATH = Join-Path $FoundryRoot "src"
$RelayArguments = @(
    "-m",
    "apf.self_improvement_relay",
    "--foundry-root",
    $FoundryRoot,
    "--repository",
    "NurionHoldings/ARKAON-Pattern-Foundry",
    "--watch-seconds",
    $WatchSeconds
)
& $Python @RelayArguments

if ($LASTEXITCODE -ne 0) {
    throw "ARKAON self-improvement relay exited with code $LASTEXITCODE"
}
