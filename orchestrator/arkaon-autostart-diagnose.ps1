param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$RuntimeScript = Join-Path $FoundryRoot "orchestrator\arkaon-runtime.ps1"
. $RuntimeScript

function Test-ScheduledTaskPresent {
    param([string]$TaskName)
    return [bool](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
}

function Get-StartupShortcutPresent {
    param([string]$ShortcutName)
    $startupFolder = [Environment]::GetFolderPath("Startup")
    return Test-Path -LiteralPath (Join-Path $startupFolder "$ShortcutName.lnk")
}

$issues = @()
$checks = @()

try {
    $python = Resolve-ArkaonPython -FoundryRoot $FoundryRoot
    $checks += [PSCustomObject]@{ id = "PYTHON_RUNTIME"; status = "PASS"; detail = $python.Source }
}
catch {
    $checks += [PSCustomObject]@{ id = "PYTHON_RUNTIME"; status = "FAIL"; detail = $_.Exception.Message }
    $issues += "PYTHON_RUNTIME"
}

$taskPresent = Test-ScheduledTaskPresent -TaskName "ARKAON_Pattern_Foundry"
$watchdogPresent = Test-ScheduledTaskPresent -TaskName "ARKAON_Watchdog"
$shortcutPresent = Get-StartupShortcutPresent -ShortcutName "ARKAON_Pattern_Foundry"

if (-not $taskPresent -and -not $shortcutPresent) {
    $checks += [PSCustomObject]@{ id = "BOOT_REGISTRATION"; status = "FAIL"; detail = "no scheduled task or startup shortcut" }
    $issues += "BOOT_REGISTRATION"
}
else {
    $checks += [PSCustomObject]@{
        id = "BOOT_REGISTRATION"
        status = "PASS"
        detail = "task=$taskPresent shortcut=$shortcutPresent watchdog=$watchdogPresent"
    }
}

if (-not $watchdogPresent) {
    $checks += [PSCustomObject]@{ id = "WATCHDOG_TASK"; status = "WARN"; detail = "watchdog task missing" }
    $issues += "WATCHDOG_TASK"
}
else {
    $checks += [PSCustomObject]@{ id = "WATCHDOG_TASK"; status = "PASS"; detail = "present" }
}

$collectorStatus = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\collector-daemon.json")
$analysisStatus = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\analysis-daemon.json")
$startupStatus = Read-ArkaonDaemonStatus -StatusPath (Join-Path $FoundryRoot "state\startup-last-run.json")

$CollectorDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-collector-daemon.ps1"
$AnalysisDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-analysis-daemon.ps1"
$collectorWorker = Test-ArkaonCollectorWorkerAlive -FoundryRoot $FoundryRoot
$analysisFresh = Test-ArkaonAnalysisCycleFresh -FoundryRoot $FoundryRoot
$collectorAlive = $collectorStatus -and (
    (Test-ArkaonDaemonProcess -ProcessId ([int]$collectorStatus.pid) -ScriptPath $CollectorDaemon) -and $collectorWorker
)
$analysisAlive = $analysisStatus -and (
    (Test-ArkaonDaemonProcess -ProcessId ([int]$analysisStatus.pid) -ScriptPath $AnalysisDaemon) -and $analysisFresh
)

$checks += [PSCustomObject]@{
    id = "COLLECTOR_DAEMON"
    status = $(if ($collectorAlive) { "PASS" } else { "FAIL" })
    detail = $(if ($collectorStatus) {
        "pid=$($collectorStatus.pid) worker=$collectorWorker started=$($collectorStatus.started_at)"
    } else { "status file missing" })
}
if (-not $collectorAlive) { $issues += "COLLECTOR_DAEMON" }

$checks += [PSCustomObject]@{
    id = "ANALYSIS_DAEMON"
    status = $(if ($analysisAlive) { "PASS" } else { "FAIL" })
    detail = $(if ($analysisStatus) {
        "pid=$($analysisStatus.pid) fresh_cycle=$analysisFresh started=$($analysisStatus.started_at)"
    } else { "status file missing" })
}
if (-not $analysisAlive) { $issues += "ANALYSIS_DAEMON" }

if ($startupStatus) {
    $checks += [PSCustomObject]@{
        id = "LAST_AUTOSTART"
        status = "PASS"
        detail = "observed=$($startupStatus.observed_at) completed=$($startupStatus.completed_at)"
    }
}
else {
    $checks += [PSCustomObject]@{ id = "LAST_AUTOSTART"; status = "FAIL"; detail = "startup-last-run.json missing" }
    $issues += "LAST_AUTOSTART"
}

$dryRun = $null
try {
    $python = Resolve-ArkaonPython -FoundryRoot $FoundryRoot
    $exitCode = Invoke-ArkaonPythonScript -Python $python -FoundryRoot $FoundryRoot `
        -ScriptPath (Join-Path $FoundryRoot "orchestrator\arkaon-orchestrator.py") `
        -ScriptArguments @("--dry-run")
    if ($exitCode -eq 0) {
        $checks += [PSCustomObject]@{ id = "ORCHESTRATOR_DRY_RUN"; status = "PASS"; detail = "exit=0" }
    }
    else {
        $checks += [PSCustomObject]@{ id = "ORCHESTRATOR_DRY_RUN"; status = "FAIL"; detail = "exit=$exitCode" }
        $issues += "ORCHESTRATOR_DRY_RUN"
    }
}
catch {
    $checks += [PSCustomObject]@{ id = "ORCHESTRATOR_DRY_RUN"; status = "FAIL"; detail = $_.Exception.Message }
    $issues += "ORCHESTRATOR_DRY_RUN"
}

$overall = if ($issues.Count -eq 0) { "PASS" } else { "FAIL" }
$report = [PSCustomObject]@{
    schema_version = "apf.autostart-diagnose.v1"
    checked_at = [DateTime]::UtcNow.ToString("o")
    foundry_root = $FoundryRoot
    overall = $overall
    issue_codes = $issues
    checks = $checks
}

$report | ConvertTo-Json -Depth 6
