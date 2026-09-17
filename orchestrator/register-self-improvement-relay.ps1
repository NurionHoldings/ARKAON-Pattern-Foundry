param(
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$Launcher = Join-Path $FoundryRoot "orchestrator\arkaon-self-improvement-relay.ps1"
if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Relay launcher not found: $Launcher"
}

$TaskName = "ARKAON Self Improvement Relay"
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -FoundryRoot "{1}"' -f $Launcher, $FoundryRoot
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$SettingsParameters = @{
    AllowStartIfOnBatteries = $true
    DontStopIfGoingOnBatteries = $true
    ExecutionTimeLimit = (New-TimeSpan -Days 365)
    RestartCount = 3
    RestartInterval = (New-TimeSpan -Minutes 1)
}
$Settings = New-ScheduledTaskSettingsSet @SettingsParameters
$TaskParameters = @{
    TaskName = $TaskName
    Action = $Action
    Trigger = $Trigger
    Settings = $Settings
    Description = "Relays validated ARKAON SELF_IMPROVEMENT_REQUEST packets to GitHub for Eternian review."
}
Register-ScheduledTask @TaskParameters -Force | Out-Null

Write-Output "Registered: $TaskName"
Write-Output "The task uses the current user's existing gh authentication and stores no token."
