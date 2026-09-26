param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$RuntimeScript = Join-Path $FoundryRoot "orchestrator\arkaon-runtime.ps1"
$Orchestrator = Join-Path $FoundryRoot "orchestrator\arkaon-orchestrator.py"
$CollectorDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-collector-daemon.ps1"
$AnalysisDaemon = Join-Path $FoundryRoot "orchestrator\arkaon-analysis-daemon.ps1"
$StartupState = Join-Path $FoundryRoot "state\startup-last-run.json"
$CollectorPolicy = Join-Path $FoundryRoot "config\collector.default.json"

. $RuntimeScript

$mutexName = "Local\ARKAON-Startup"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "startup skipped because another startup is active"
    return
}

$startedAt = [DateTime]::UtcNow.ToString("o")
$collectorEnabled = $false
$collectorVerified = $false
$analysisVerified = $false
$orchestratorExitCode = 1
$errorMessage = $null

try {
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "autostart beginning at $startedAt"

    $collectorEnabled = $false
    if (Test-Path -LiteralPath $CollectorPolicy) {
        $policy = Get-Content -LiteralPath $CollectorPolicy -Raw -Encoding UTF8 | ConvertFrom-Json
        $collectorEnabled = [bool]$policy.enabled
    }

    if ($collectorEnabled) {
        $collectorResult = Start-ArkaonDaemonProcess -FoundryRoot $FoundryRoot -DaemonName "collector-daemon" -ScriptPath $CollectorDaemon
        $collectorVerified = $collectorResult.verified
    }

    $analysisResult = Start-ArkaonDaemonProcess -FoundryRoot $FoundryRoot -DaemonName "analysis-daemon" -ScriptPath $AnalysisDaemon
    $analysisVerified = $analysisResult.verified

    $python = Resolve-ArkaonPython -FoundryRoot $FoundryRoot
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "orchestrator immediate run using $($python.Source)"
    $orchestratorExitCode = Invoke-ArkaonPythonScript -Python $python -FoundryRoot $FoundryRoot -ScriptPath $Orchestrator
    if ($orchestratorExitCode -ne 0) {
        throw "Central orchestrator failed with exit code $orchestratorExitCode"
    }

    $status = "PASS"
}
catch {
    $status = "FAIL"
    $errorMessage = $_.Exception.Message
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "autostart failure: $errorMessage"
}
finally {
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $StartupState) | Out-Null
    @{
        schema_version = "apf.orchestrator-startup.v3"
        observed_at = $startedAt
        completed_at = [DateTime]::UtcNow.ToString("o")
        foundry_root = $FoundryRoot
        source = "WINDOWS_LOGON_AUTOSTART"
        status = $status
        error = $errorMessage
        collector_daemon_started = $collectorEnabled
        collector_daemon_verified = $collectorVerified
        analysis_daemon_started = $true
        analysis_daemon_verified = $analysisVerified
        orchestrator_exit_code = $orchestratorExitCode
        machine_identifier_collected = $false
        automatic_learning = $false
        production_change_allowed = $false
    } | ConvertTo-Json | Set-Content -LiteralPath $StartupState -Encoding UTF8

    if ($mutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
}

if ($status -eq "FAIL") {
    throw $errorMessage
}

Write-Output "ARKAON autostart completed. Review inbox\eternian-review before any change."
