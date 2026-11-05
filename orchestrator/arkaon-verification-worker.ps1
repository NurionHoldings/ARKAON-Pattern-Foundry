param(
    [string]$FoundryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$RequestId = "main-integration-20261105-verify-v2",
    [switch]$BuildImage,
    [switch]$ConnectRelay,
    [int]$WatchSeconds = 0
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $FoundryRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker with Linux containers is required; no host execution fallback." }
if ($RequestId -notmatch '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$') { throw "Invalid request id" }
$Python = Join-Path $FoundryRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = (Get-Command python -ErrorAction Stop).Source }
if ($BuildImage) {
    docker build -f Dockerfile.verification-worker -t arkaon-verification-worker .
    if ($LASTEXITCODE -ne 0) { throw "Verification image build failed" }
}
$ImageId = (docker image inspect arkaon-verification-worker --format '{{.Id}}').Trim()
if ($LASTEXITCODE -ne 0 -or $ImageId -notmatch '^sha256:[0-9a-f]{64}$') { throw "Pinned local verification image is required" }
$SourceSha = (git log -1 --format=%H -- "approvals/self-improvement/$RequestId.json").Trim()
if ($LASTEXITCODE -ne 0 -or $SourceSha -notmatch '^[0-9a-f]{40}$') { throw "Approved immutable request source is unavailable" }
$env:PYTHONPATH = Join-Path $FoundryRoot "src"
if ($ConnectRelay) {
    $ConnectionPath = Join-Path $FoundryRoot "state\verification-worker-connection.json"
    New-Item -ItemType Directory -Force -Path (Split-Path $ConnectionPath) | Out-Null
    $Connection = @{ schema_version = "apf.verification-worker-connection/v1"; image_id = $ImageId; request_id = $RequestId }
    $Json = $Connection | ConvertTo-Json
    $Utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText("$ConnectionPath.tmp", $Json, $Utf8)
    Move-Item -LiteralPath "$ConnectionPath.tmp" -Destination $ConnectionPath -Force
}
do {
    & $Python -m apf.verification_worker --foundry-root $FoundryRoot --repository-root $FoundryRoot --image $ImageId --worker-id arkaon-pc-verifier --seed-request $RequestId --approval-source-sha $SourceSha
    if ($LASTEXITCODE -ne 0) { throw "Verification blocked or failed; inspect state/verification-worker. No automatic retry of interrupted work." }
    if ($WatchSeconds -gt 0) { Start-Sleep -Seconds ([Math]::Max($WatchSeconds, 5)) }
} while ($WatchSeconds -gt 0)
