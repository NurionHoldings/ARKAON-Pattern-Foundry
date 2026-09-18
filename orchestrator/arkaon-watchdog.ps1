param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$RuntimeScript = Join-Path $FoundryRoot "orchestrator\arkaon-runtime.ps1"
$StartupScript = Join-Path $FoundryRoot "orchestrator\arkaon-startup.ps1"
$CollectorDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-collector-daemon.ps1"
$AnalysisDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-analysis-daemon.ps1"
$CollectorPolicy = Join-Path $FoundryRoot "config\collector.default.json"
$WatchdogState = Join-Path $FoundryRoot "state\watchdog-last-run.json"

. $RuntimeScript

$checkedAt = [DateTime]::UtcNow.ToString("o")
Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "watchdog check at $checkedAt"

$collectorEnabled = $false
if (Test-Path -LiteralPath $CollectorPolicy) {
    $policy = Get-Content -LiteralPath $CollectorPolicy -Raw -Encoding UTF8 | ConvertFrom-Json
    $collectorEnabled = [bool]$policy.enabled
}

$collectorStatus = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\collector-daemon.json")
$analysisStatus = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\analysis-daemon.json")

$collectorAlive = $collectorStatus -and (Test-ArkaonProcessAlive -ProcessId ([int]$collectorStatus.pid))
$analysisAlive = $analysisStatus -and (Test-ArkaonProcessAlive -ProcessId ([int]$analysisStatus.pid))

$actions = @()

if ($collectorEnabled -and -not $collectorAlive) {
    $result = Start-ArkaonDaemonProcess -FoundryRoot $FoundryRoot -DaemonName "collector-daemon" -ScriptPath $CollectorDaemon
    $actions += "collector_restart pid=$($result.pid) verified=$($result.verified)"
}

if (-not $analysisAlive) {
    $result = Start-ArkaonDaemonProcess -FoundryRoot $FoundryRoot -DaemonName "analysis-daemon" -ScriptPath $AnalysisDaemon
    $actions += "analysis_restart pid=$($result.pid) verified=$($result.verified)"
}

$startupState = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\startup-last-run.json")
$startupStale = $true
if ($startupState -and $startupState.completed_at) {
    $completedAt = [DateTime]::Parse($startupState.completed_at).ToUniversalTime()
    $startupStale = ((Get-Date).ToUniversalTime() - $completedAt).TotalHours -gt 24
}

if ($startupStale -and -not $collectorAlive -and -not $analysisAlive) {
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "watchdog invoking full autostart because daemons and recent startup are missing"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $StartupScript, "-FoundryRoot", $FoundryRoot) `
        -WorkingDirectory $FoundryRoot `
        -WindowStyle Hidden | Out-Null
    $actions += "full_autostart_requested"
}

@{
    schema_version = "apf.watchdog.v1"
    checked_at = $checkedAt
    collector_enabled = $collectorEnabled
    collector_alive = $collectorAlive
    analysis_alive = $analysisAlive
    actions = $actions
} | ConvertTo-Json | Set-Content -LiteralPath $WatchdogState -Encoding UTF8
