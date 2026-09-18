param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "plan", "archive")]
    [string]$Action = "status",
    [int]$BatchSize = 30,
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$Python = Join-Path $FoundryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}

$env:PYTHONPATH = Join-Path $FoundryRoot "src"
$Arguments = @(
    "-m", "apf.mailbox_maintenance",
    "--foundry-root", $FoundryRoot,
    "--batch-size", $BatchSize
)

if ($Action -eq "status") {
    $Arguments += "--summary"
}
elseif ($Action -eq "archive") {
    $Arguments += @("--apply-archive", "--summary")
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Mailbox management failed with code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Action: $Action"
Write-Host "Report: $FoundryRoot\state\mailbox-maintenance-latest.json"
