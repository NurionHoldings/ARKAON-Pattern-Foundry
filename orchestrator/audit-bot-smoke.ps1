param(
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [Parameter(Mandatory = $true)][string]$ExpectedCommit
)

$ErrorActionPreference = "Stop"
$Preflight = Join-Path $FoundryRoot "orchestrator\audit-bot-preflight.ps1"
& $Preflight -FoundryRoot $FoundryRoot -ExpectedCommit $ExpectedCommit -RequireActiveBaseline

$TaskName = "ARKAON Self Improvement Relay"
if ((Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop).State -ne "Running") {
    Start-ScheduledTask -TaskName $TaskName
}
Start-Sleep -Seconds 3
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$Info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop
if ($Task.State -notin @("Running", "Ready")) { throw "SMOKE_TASK_STATE_INVALID: $($Task.State)" }
if ($Info.LastTaskResult -ne 0 -and $Task.State -ne "Running") {
    throw "SMOKE_TASK_RESULT_FAILED: $($Info.LastTaskResult)"
}
Write-Output "SMOKE_PASS state=$($Task.State) lastResult=$($Info.LastTaskResult)"
