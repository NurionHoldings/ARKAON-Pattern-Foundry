param([string]$FoundryRoot = (Split-Path -Parent $PSScriptRoot), [string]$Python = 'python', [switch]$Once)
$ErrorActionPreference = 'Stop'
Push-Location $FoundryRoot
try {
  & $Python -m apf.agent_exchange preflight
  if ($LASTEXITCODE -ne 0) { throw 'Agent exchange preflight failed' }
  if ($Once) { & $Python -m apf.agent_exchange watch --foundry-root $FoundryRoot --once }
  else { & $Python -m apf.agent_exchange watch --foundry-root $FoundryRoot --seconds 15 }
  if ($LASTEXITCODE -ne 0) { throw 'Agent exchange courier failed' }
} finally { Pop-Location }
