param(
    [string]$FoundryRoot = "D:\ARKAON_Pattern Foundry"
)

$ErrorActionPreference = "Stop"
$FoundryRoot = (Resolve-Path -LiteralPath $FoundryRoot).Path
$StartupScript = Join-Path $FoundryRoot "orchestrator\arkaon-startup.ps1"

if (-not (Test-Path -LiteralPath $StartupScript)) {
    throw "Startup script not found: $StartupScript"
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$mutexName = "Local\ARKAON-Central-Orchestrator-Launcher"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0, $false)) {
    return
}

try {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "ARKAON"
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    $transparent = [System.Drawing.Color]::Magenta
    $form.BackColor = $transparent
    $form.TransparencyKey = $transparent
    $form.Size = New-Object System.Drawing.Size(112, 112)

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        ($screen.Right - $form.Width - 18),
        ($screen.Bottom - $form.Height - 18)
    )

    $button = New-Object System.Windows.Forms.Button
    $button.Text = [char]0x2764
    $button.Dock = [System.Windows.Forms.DockStyle]::Fill
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderSize = 0
    $button.FlatAppearance.MouseOverBackColor = $transparent
    $button.FlatAppearance.MouseDownBackColor = $transparent
    $button.UseVisualStyleBackColor = $false
    $button.BackColor = $transparent
    $button.ForeColor = [System.Drawing.Color]::FromArgb(255, 255, 77, 106)
    $button.Cursor = [System.Windows.Forms.Cursors]::Hand
    $button.Font = New-Object System.Drawing.Font(
        "Segoe UI Emoji",
        44,
        [System.Drawing.FontStyle]::Regular,
        [System.Drawing.GraphicsUnit]::Point
    )
    $button.AccessibleName = "아르카온 실행"
    $button.AccessibleDescription = "클릭하면 ARKAON 중앙 오케스트레이터를 실행합니다."

    $script:running = $false
    $button.Add_Click({
        if ($script:running) {
            return
        }
        $script:running = $true
        $form.Hide()

        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden",
            "-File", $StartupScript,
            "-FoundryRoot", $FoundryRoot
        ) -WorkingDirectory $FoundryRoot | Out-Null

        $form.Close()
    })

    $form.Controls.Add($button)
    $form.Add_Shown({ $form.Activate() | Out-Null })
    [void]$form.ShowDialog()
}
finally {
    if ($mutex) {
        $mutex.ReleaseMutex() | Out-Null
        $mutex.Dispose()
    }
}
