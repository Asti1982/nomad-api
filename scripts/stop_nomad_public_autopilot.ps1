$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$runtimeDir = Join-Path $root "tools\\nomad-live"

foreach ($name in @("autopilot.pid", "cloudflared.pid")) {
  $path = Join-Path $runtimeDir $name
  if (-not (Test-Path $path)) {
    continue
  }
  $pidValue = (Get-Content $path -Raw).Trim()
  if ($pidValue) {
    Stop-Process -Id ([int]$pidValue) -Force -ErrorAction SilentlyContinue
    Write-Output "stopped_$name=$pidValue"
  }
  Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}
