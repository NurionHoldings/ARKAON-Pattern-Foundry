param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("candidate", "activate", "verify")]
    [string]$Command,
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$CommitSha = "",
    [string]$CandidatePath = "",
    [string]$ApprovalReceiptPath = ""
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $FoundryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
$env:PYTHONPATH = Join-Path $FoundryRoot "src"
$Policy = Join-Path $FoundryRoot "config\arkaon-audit-bot.json"
$Candidate = if ($CandidatePath) { $CandidatePath } else {
    Join-Path $FoundryRoot "state\audit-bot-deployment-baseline.candidate.json"
}
$Active = Join-Path $FoundryRoot "state\audit-bot-deployment-baseline.json"

switch ($Command) {
    "candidate" {
        if (-not $CommitSha) { throw "BASELINE_COMMIT_SHA_REQUIRED" }
        & $Python -m apf.audit_baseline_cli candidate --repository-root $FoundryRoot `
            --policy $Policy --commit-sha $CommitSha --output $Candidate
    }
    "activate" {
        if (-not $ApprovalReceiptPath) { throw "BASELINE_APPROVAL_RECEIPT_REQUIRED" }
        & $Python -m apf.audit_baseline_cli activate --candidate $Candidate `
            --approval-receipt $ApprovalReceiptPath --output $Active
    }
    "verify" {
        & $Python -m apf.audit_baseline_cli verify --foundry-root $FoundryRoot `
            --repository-root $FoundryRoot --policy $Policy --baseline $Active
    }
}
if ($LASTEXITCODE -ne 0) { throw "AUDIT_BASELINE_COMMAND_FAILED: $Command" }
