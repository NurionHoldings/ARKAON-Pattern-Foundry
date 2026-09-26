param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry",
    [string]$TaskName = "ARKAON_Pattern_Foundry",
    [string]$WatchdogTaskName = "ARKAON_Watchdog",
    [ValidateSet("Auto", "TaskScheduler", "StartupFolder", "All")]
    [string]$Method = "All",
    [switch]$KeepLauncherShortcut
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$StartupScript = Join-Path $FoundryRoot "orchestrator\arkaon-startup.ps1"
$WatchdogScript = Join-Path $FoundryRoot "orchestrator\arkaon-watchdog.ps1"
$LauncherScript = Join-Path $FoundryRoot "orchestrator\arkaon-launcher.ps1"
$LegacyTaskNames = @("ARKAON-Central-Orchestrator")

if (-not (Test-Path -LiteralPath $StartupScript)) {
    throw "Startup script not found: $StartupScript"
}
if (-not (Test-Path -LiteralPath $WatchdogScript)) {
    throw "Watchdog script not found: $WatchdogScript"
}

function Remove-LegacyStartupEntries {
    foreach ($legacyName in $LegacyTaskNames) {
        $existing = Get-ScheduledTask -TaskName $legacyName -ErrorAction SilentlyContinue
        if ($existing) {
            Unregister-ScheduledTask -TaskName $legacyName -Confirm:$false
            Write-Output "Removed legacy scheduled task '$legacyName'."
        }
    }

    $startupFolder = [Environment]::GetFolderPath("Startup")
    $legacyShortcut = Join-Path $startupFolder "ARKAON-Central-Orchestrator.lnk"
    if (Test-Path -LiteralPath $legacyShortcut) {
        Remove-Item -LiteralPath $legacyShortcut -Force
        Write-Output "Removed legacy startup shortcut at $legacyShortcut."
    }
}

function Install-StartupFolderShortcut {
    param(
        [string]$ShortcutName,
        [string]$TargetScript
    )

    $startupFolder = [Environment]::GetFolderPath("Startup")
    $shortcutPath = Join-Path $startupFolder "$ShortcutName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$TargetScript`" -FoundryRoot `"$FoundryRoot`""
    $shortcut.WorkingDirectory = $FoundryRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "ARKAON automatic collection and analysis at Windows logon"
    $shortcut.Save()
    return $shortcutPath
}

function New-ArkaonTaskSettings {
    return New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)
}

function Install-AutostartScheduledTask {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
        "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartupScript`" -FoundryRoot `"$FoundryRoot`""
    )
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ArkaonTaskSettings
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

function Install-WatchdogScheduledTask {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (
        "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`" -FoundryRoot `"$FoundryRoot`""
    )
    $settings = New-ArkaonTaskSettings
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $WatchdogTaskName `
        -Action $action `
        -Trigger @(
            (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME),
            (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue))
        ) `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null
}

Remove-LegacyStartupEntries

$installTask = $Method -in @("Auto", "TaskScheduler", "All")
$installShortcut = $Method -in @("Auto", "StartupFolder", "All")
$errors = @()

if ($installTask) {
    try {
        Install-AutostartScheduledTask
        Write-Output "Registered scheduled task '$TaskName'."
    }
    catch {
        $errors += "autostart task: $($_.Exception.Message)"
    }

    try {
        Install-WatchdogScheduledTask
        Write-Output "Registered watchdog task '$WatchdogTaskName' (logon + every 5 minutes)."
    }
    catch {
        $errors += "watchdog task: $($_.Exception.Message)"
    }
}

if ($installShortcut) {
    try {
        $shortcut = Install-StartupFolderShortcut -ShortcutName $TaskName -TargetScript $StartupScript
        Write-Output "Registered startup shortcut at $shortcut."
    }
    catch {
        $errors += "startup shortcut: $($_.Exception.Message)"
    }
}

if ($KeepLauncherShortcut -and (Test-Path -LiteralPath $LauncherScript)) {
    $launcherShortcut = Install-StartupFolderShortcut -ShortcutName "ARKAON-Manual-Launcher" -TargetScript $LauncherScript
    Write-Output "Optional manual launcher shortcut registered at $launcherShortcut."
}

if ($errors.Count -gt 0 -and -not ($installTask -and $installShortcut)) {
    throw ($errors -join "; ")
}
if ($errors.Count -gt 0) {
    Write-Output "Partial registration warnings: $($errors -join '; ')"
}

Write-Output "Autostart entrypoint: $StartupScript"
Write-Output "Watchdog entrypoint: $WatchdogScript"
Write-Output "Diagnose with: powershell.exe -File `"$FoundryRoot\orchestrator\arkaon-autostart-diagnose.ps1`""
