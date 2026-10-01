param(
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$ExpectedCommit = "",
    [switch]$RequireActiveBaseline
)

$ErrorActionPreference = "Stop"
$ExpectedTask = "ARKAON Self Improvement Relay"
$Policy = Join-Path $FoundryRoot "config\arkaon-audit-bot.json"
$Baseline = Join-Path $FoundryRoot "state\audit-bot-deployment-baseline.json"
$Launcher = Join-Path $FoundryRoot "orchestrator\arkaon-self-improvement-relay.ps1"
$Python = Join-Path $FoundryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
foreach ($Path in @($Policy, $Launcher)) {
    if (-not (Test-Path -LiteralPath $Path)) { throw "PREFLIGHT_REQUIRED_PATH_MISSING: $Path" }
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "PREFLIGHT_GH_MISSING" }
gh auth status | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PREFLIGHT_GH_AUTH_INVALID" }

$Head = (& git -C $FoundryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "PREFLIGHT_GIT_HEAD_INVALID" }
if ($ExpectedCommit -and $Head -ne $ExpectedCommit) { throw "PREFLIGHT_HEAD_MISMATCH: $Head" }
$TrackedChanges = & git -C $FoundryRoot status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0 -or $TrackedChanges) { throw "PREFLIGHT_TRACKED_WORKTREE_DIRTY" }

$Task = Get-ScheduledTask -TaskName $ExpectedTask -ErrorAction Stop
$TaskCommand = "$($Task.Actions.Execute) $($Task.Actions.Arguments)"
if ($TaskCommand -notlike "*$Launcher*") { throw "PREFLIGHT_TASK_ACTION_MISMATCH" }

$env:PYTHONPATH = Join-Path $FoundryRoot "src"
if (Test-Path -LiteralPath $Baseline) {
    & $Python -m apf.audit_baseline_cli verify --foundry-root $FoundryRoot `
        --repository-root $FoundryRoot --policy $Policy --baseline $Baseline
    if ($LASTEXITCODE -ne 0) { throw "PREFLIGHT_BASELINE_VERIFY_FAILED" }
} else {
    if ($RequireActiveBaseline) { throw "PREFLIGHT_DEPLOYMENT_BASELINE_REQUIRED" }
    Write-Output "HOLD:DEPLOYMENT_BASELINE_MISSING"
}
Write-Output "PREFLIGHT_PASS commit=$Head task=$ExpectedTask"
