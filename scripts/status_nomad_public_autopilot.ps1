$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $root "tools\\nomad-live"

$publicUrl = ""
$port = ""
$tunnelMode = ""
if (Test-Path (Join-Path $runtimeDir "public-url.txt")) {
  $publicUrl = (Get-Content (Join-Path $runtimeDir "public-url.txt") -Raw).Trim()
}
if (Test-Path (Join-Path $runtimeDir "port.txt")) {
  $port = (Get-Content (Join-Path $runtimeDir "port.txt") -Raw).Trim()
}
if (Test-Path (Join-Path $runtimeDir "tunnel-mode.txt")) {
  $tunnelMode = (Get-Content (Join-Path $runtimeDir "tunnel-mode.txt") -Raw).Trim()
}

Write-Output "PUBLIC_URL=$publicUrl"
Write-Output "PORT=$port"
Write-Output "TUNNEL_MODE=$tunnelMode"

foreach ($name in @("autopilot.pid", "cloudflared.pid")) {
  $path = Join-Path $runtimeDir $name
  if (Test-Path $path) {
    $pidValue = (Get-Content $path -Raw).Trim()
    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    Write-Output "$name=$pidValue"
    Write-Output ($name + "_running=" + [bool]$process)
  }
}

if ($publicUrl) {
  try {
    $health = Invoke-WebRequest -Uri "$publicUrl/health" -UseBasicParsing -TimeoutSec 15
    Write-Output "HEALTH_STATUS=$($health.StatusCode)"
  } catch {
    Write-Output "HEALTH_STATUS=ERROR"
  }
  try {
    $card = Invoke-WebRequest -Uri "$publicUrl/.well-known/agent-card.json" -UseBasicParsing -TimeoutSec 15
    Write-Output "AGENT_CARD_STATUS=$($card.StatusCode)"
  } catch {
    Write-Output "AGENT_CARD_STATUS=ERROR"
  }
}
