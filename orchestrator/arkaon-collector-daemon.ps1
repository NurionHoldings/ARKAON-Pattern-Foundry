param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$RuntimeScript = Join-Path $FoundryRoot "orchestrator\arkaon-runtime.ps1"
$ConfigPath = Join-Path $FoundryRoot "config\collector.default.json"
$AuditPath = Join-Path $FoundryRoot "state\arkaon-collection-audit.jsonl"
$StatePath = Join-Path $FoundryRoot "state\arkaon-collection-state.sqlite3"
$LogPath = Join-Path $FoundryRoot "logs\collector-daemon.log"
$StatusPath = Join-Path $FoundryRoot "state\collector-daemon.json"

. $RuntimeScript

$mutexName = "Local\ARKAON-Collector-Daemon"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
    exit 0
}

try {
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $LogPath) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $AuditPath) | Out-Null

    $startedAt = [DateTime]::UtcNow.ToString("o")
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "collector daemon pid=$PID starting at $startedAt"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "collector daemon starting at $startedAt pid=$PID"
    @{
        schema_version = "apf.collector-daemon.v1"
        pid = $PID
        started_at = $startedAt
        foundry_root = $FoundryRoot
        config_path = $ConfigPath
    } | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8

    $python = Resolve-ArkaonPython -FoundryRoot $FoundryRoot
    $SchedulePath = Join-Path $FoundryRoot "config\arkaon-hourly-learning-schedule.json"
    $moduleArgs = @(
        "apf.collector_service",
        "--config", $ConfigPath,
        "--audit", $AuditPath,
        "--state", $StatePath,
        "--foundry-root", $FoundryRoot
    )
    if (Test-Path -LiteralPath $SchedulePath) {
        $moduleArgs += @("--schedule", $SchedulePath)
    }
    $exitCode = Invoke-ArkaonPythonModule -Python $python -FoundryRoot $FoundryRoot -ModuleArguments $moduleArgs
    if ($exitCode -ne 0) {
        throw "collector_service exited with code $exitCode"
    }
}
catch {
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "collector daemon failure: $_"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "collector daemon failure: $_"
    throw
}
finally {
    if ($mutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
}
