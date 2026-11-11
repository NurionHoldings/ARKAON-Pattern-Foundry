# ASIA HOLDINGS cinema end-to-end local run (PR-C).
# validate inputs -> build .blend -> scene invariants -> PNG sequence -> MP4 -> verify -> SHA chain.
# The final 1080p profile requires typing the approval string, so it never runs unattended by accident.
param(
    [ValidateSet("preview", "final")] [string]$Profile = "preview",
    [Parameter(Mandatory = $true)] [string]$Manifest,
    [Parameter(Mandatory = $true)] [string]$RunId,
    [string]$Approve = "",
    [string]$Blender = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    [string]$WorkDir = "private/asia-cinema/pr-c-build"
)
$ErrorActionPreference = "Stop"
$ApprovalString = "APPROVE ASIA FINAL RENDER"

if ($Profile -eq "final" -and $Approve -ne $ApprovalString) {
    $Approve = Read-Host "Type '$ApprovalString' to render the final 1080p profile"
    if ($Approve -ne $ApprovalString) { throw "final render not approved" }
}

$size = @{ preview = @(960, 540); final = @(1920, 1080) }[$Profile]
$evidence = "inbox/eternian-review/$RunId"
$blend = Join-Path $WorkDir "asia_holdings_cinema.blend"
$frames = Join-Path $WorkDir "frames_$Profile"
$video = Join-Path $WorkDir "asia_holdings_cinema_$Profile.mp4"
New-Item -ItemType Directory -Force $evidence, $WorkDir | Out-Null

function Invoke-Step([string]$Name, [scriptblock]$Body) {
    Write-Host "== $Name"
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit $LASTEXITCODE)" }
}

Invoke-Step "validate inputs" { python -m modules.asia_cinema.validate_inputs --manifest $Manifest --repo-root . --report "$evidence/input-validation-report.json" }
Invoke-Step "build scene" { & $Blender -b --factory-startup -P modules/asia_cinema/blender/build_scene.py -- --manifest $Manifest --repo-root . --out-blend $blend }
Invoke-Step "scene invariants" { & $Blender -b $blend -P modules/asia_cinema/blender/validate_scene_invariants.py -- --manifest $Manifest --repo-root . --report "$evidence/scene-invariants-report.json" }
if (Test-Path $frames) { Get-ChildItem $frames -Filter "frame_*.png" | Remove-Item }
Invoke-Step "export frames" { & $Blender -b $blend -P modules/asia_cinema/blender/export_png_sequence.py -- --out-dir $frames --width $size[0] --height $size[1] }
Invoke-Step "encode mp4" { python -m modules.asia_cinema.pipeline.encode_mp4 --frames $frames --profile $Profile --out $video }
Invoke-Step "verify mp4" { python -m modules.asia_cinema.pipeline.verify_output --video $video --profile $Profile --report "$evidence/output-verification-$Profile.json" }
Invoke-Step "sha chain" { python -m modules.asia_cinema.pipeline.chain_manifest --run-id $RunId --profile $Profile --manifest $Manifest --blend $blend --frames $frames --video $video --evidence-dir $evidence }
Write-Host "RUN_OK $Profile $video"
