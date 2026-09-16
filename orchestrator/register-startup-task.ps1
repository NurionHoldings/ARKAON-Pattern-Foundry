param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry",
    [string]$TaskName = "ARKAON_Pattern_Foundry",
    [ValidateSet("Auto", "TaskScheduler", "StartupFolder")]
    [string]$Method = "Auto"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$LauncherScript = Join-Path $FoundryRoot "orchestrator\arkaon-launcher.ps1"

if (-not (Test-Path -LiteralPath $LauncherScript)) {
    throw "Launcher script not found: $LauncherScript"
}

$command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$LauncherScript`" -FoundryRoot `"$FoundryRoot`""

function Install-StartupFolderShortcut {
    $startupFolder = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupFolder "$TaskName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$LauncherScript`" -FoundryRoot `"$FoundryRoot`""
    $shortcut.WorkingDirectory = $FoundryRoot
    $shortcut.WindowStyle = 1
    $shortcut.Description = "ARKAON central orchestrator at Windows logon"
    $shortcut.Save()
    return $shortcutPath
}

function Install-ScheduledTaskCmdlet {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
        "-NoProfile -ExecutionPolicy Bypass -File `"$LauncherScript`" -FoundryRoot `"$FoundryRoot`""
    )
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::FromMinutes(30))
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
}

function Install-SchtasksEntry {
    $existing = schtasks /Query /TN $TaskName 2>$null
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN $TaskName /F | Out-Null
    }
    schtasks /Create `
        /TN $TaskName `
        /TR $command `
        /SC ONLOGON `
        /RL LIMITED `
        /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks registration failed with exit code $LASTEXITCODE"
    }
}

$methods = switch ($Method) {
    "TaskScheduler" { @("TaskScheduler", "StartupFolder") }
    "StartupFolder" { @("StartupFolder") }
    default { @("TaskScheduler", "StartupFolder") }
}

$lastError = $null
foreach ($candidate in $methods) {
    try {
        if ($candidate -eq "TaskScheduler") {
            try {
                Install-ScheduledTaskCmdlet
                Write-Output "Registered scheduled task '$TaskName' via Register-ScheduledTask for $FoundryRoot"
                return
            }
            catch {
                Install-SchtasksEntry
                Write-Output "Registered scheduled task '$TaskName' via schtasks for $FoundryRoot"
                return
            }
        }
        if ($candidate -eq "StartupFolder") {
            $shortcut = Install-StartupFolderShortcut
            Write-Output "Registered startup shortcut at $shortcut (no administrator rights required)"
            return
        }
    }
    catch {
        $lastError = $_
    }
}

if ($lastError) {
    throw $lastError
}

throw "Startup registration failed"
