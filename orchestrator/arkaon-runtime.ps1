function Resolve-ArkaonPython {
    param(
        [string]$FoundryRoot
    )

    $cachePath = Join-Path $FoundryRoot "state\python-runtime.json"
    if (Test-Path -LiteralPath $cachePath) {
        try {
            $cached = Get-Content -LiteralPath $cachePath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($cached.executable -and (Test-Path -LiteralPath $cached.executable)) {
                return [PSCustomObject]@{
                    Source = $cached.executable
                    Arguments = @($cached.arguments | ForEach-Object { [string]$_ })
                }
            }
        }
        catch {
            # fall through to discovery
        }
    }

    $candidates = @(
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "python3"; Arguments = @() }
    )

    $env:PYTHONPATH = Join-Path $FoundryRoot "src"
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Command -ErrorAction SilentlyContinue
        if (-not $command) {
            continue
        }
        $argumentList = @($candidate.Arguments + @("-c", "import apf.collector_service"))
        & $command.Source @argumentList 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $resolved = [PSCustomObject]@{
                Source = $command.Source
                Arguments = @($candidate.Arguments | ForEach-Object { [string]$_ })
            }
            New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $cachePath) | Out-Null
            @{
                schema_version = "apf.python-runtime.v1"
                executable = $resolved.Source
                arguments = $resolved.Arguments
                resolved_at = [DateTime]::UtcNow.ToString("o")
            } | ConvertTo-Json | Set-Content -LiteralPath $cachePath -Encoding UTF8
            return $resolved
        }
    }

    throw "Python 3.11+ with apf package path was not found."
}

function Write-ArkaonAutostartLog {
    param(
        [Parameter(Mandatory = $true)][string]$FoundryRoot,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $logPath = Join-Path $FoundryRoot "logs\autostart.log"
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $logPath) | Out-Null
    $line = "{0} {1}" -f ([DateTime]::UtcNow.ToString("o")), $Message
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value $line
}

function Test-ArkaonProcessAlive {
    param(
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return $false
    }
    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Read-ArkaonDaemonStatus {
    param(
        [Parameter(Mandatory = $true)][string]$StatusPath
    )

    if (-not (Test-Path -LiteralPath $StatusPath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Start-ArkaonDaemonProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FoundryRoot,
        [Parameter(Mandatory = $true)][string]$DaemonName,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [hashtable]$ExtraArguments = @{},
        [int]$VerifySeconds = 8
    )

    $statusPath = Join-Path $FoundryRoot "state\$DaemonName.json"
    $existing = Read-ArkaonDaemonStatus -StatusPath $statusPath
    if ($existing -and (Test-ArkaonProcessAlive -ProcessId ([int]$existing.pid))) {
        Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "$DaemonName already running pid=$($existing.pid)"
        return [PSCustomObject]@{ started = $false; pid = [int]$existing.pid; verified = $true }
    }

    $argumentList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $ScriptPath,
        "-FoundryRoot", $FoundryRoot
    )
    foreach ($key in $ExtraArguments.Keys) {
        $argumentList += "-$key"
        $argumentList += [string]$ExtraArguments[$key]
    }

    $process = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $argumentList `
        -WorkingDirectory $FoundryRoot `
        -WindowStyle Hidden `
        -PassThru

    $verified = $false
    for ($elapsed = 0; $elapsed -lt $VerifySeconds; $elapsed++) {
        Start-Sleep -Seconds 1
        if (-not (Test-ArkaonProcessAlive -ProcessId $process.Id)) {
            break
        }
        $status = Read-ArkaonDaemonStatus -StatusPath $statusPath
        if ($status -and [int]$status.pid -eq $process.Id) {
            $verified = $true
            break
        }
    }

    if (-not $verified) {
        Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "$DaemonName failed verification pid=$($process.Id) exited=$($process.HasExited)"
    }
    else {
        Write-ArkaonAutostartLog -FoundryRoot $FoundryRoot -Message "$DaemonName verified pid=$($process.Id)"
    }

    return [PSCustomObject]@{
        started = $true
        pid = $process.Id
        verified = $verified
    }
}

function Invoke-ArkaonPythonModule {
    param(
        [Parameter(Mandatory = $true)]$Python,
        [Parameter(Mandatory = $true)][string]$FoundryRoot,
        [Parameter(Mandatory = $true)][string[]]$ModuleArguments
    )

    $env:PYTHONPATH = Join-Path $FoundryRoot "src"
    $argumentList = @()
    if ($Python.Arguments) {
        $argumentList += $Python.Arguments
    }
    $argumentList += @("-m") + $ModuleArguments
    & $Python.Source @argumentList | Out-Null
    return [int]$LASTEXITCODE
}

function Invoke-ArkaonPythonScript {
    param(
        [Parameter(Mandatory = $true)]$Python,
        [Parameter(Mandatory = $true)][string]$FoundryRoot,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [string[]]$ScriptArguments = @()
    )

    $env:PYTHONPATH = Join-Path $FoundryRoot "src"
    $argumentList = @()
    if ($Python.Arguments) {
        $argumentList += $Python.Arguments
    }
    $argumentList += @((Resolve-Path -LiteralPath $ScriptPath).Path) + $ScriptArguments
    & $Python.Source @argumentList | Out-Null
    return [int]$LASTEXITCODE
}
