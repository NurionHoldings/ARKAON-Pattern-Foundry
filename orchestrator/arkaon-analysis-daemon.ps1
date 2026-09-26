param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry",
    [int]$IntervalSeconds = 900
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$RuntimeScript = Join-Path $FoundryRoot "orchestrator\arkaon-runtime.ps1"
$Orchestrator = Join-Path $FoundryRoot "orchestrator\arkaon-orchestrator.py"
$LogPath = Join-Path $FoundryRoot "logs\analysis-daemon.log"
$StatusPath = Join-Path $FoundryRoot "state\analysis-daemon.json"

. $RuntimeScript

$mutexName = "Local\ARKAON-Analysis-Daemon"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
    exit 0
}

try {
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $LogPath) | Out-Null

    $startedAt = [DateTime]::UtcNow.ToString("o")
    Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "analysis daemon pid=$PID starting at $startedAt"
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "analysis daemon starting at $startedAt pid=$PID interval=${IntervalSeconds}s"
    @{
        schema_version = "apf.analysis-daemon.v1"
        pid = $PID
        started_at = $startedAt
        foundry_root = $FoundryRoot
        interval_seconds = $IntervalSeconds
    } | ConvertTo-Json | Set-Content -LiteralPath $StatusPath -Encoding UTF8

    $python = Resolve-ArkaonPython -FoundryRoot $FoundryRoot

    while ($true) {
        Start-Sleep -Seconds $IntervalSeconds
        $cycleAt = [DateTime]::UtcNow.ToString("o")
        Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "orchestrator cycle at $cycleAt"
        try {
            $exitCode = Invoke-ArkaonPythonScript -Python $python -FoundryRoot $FoundryRoot -ScriptPath $Orchestrator
            if ($exitCode -ne 0) {
                Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "orchestrator exit code $exitCode"
            }
        }
        catch {
            Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value "orchestrator failure: $_"
        }
    }
}
finally {
    if ($mutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
}
