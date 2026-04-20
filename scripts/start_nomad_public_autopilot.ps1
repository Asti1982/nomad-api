param(
  [string]$Objective = "Ask public agents for compute/auth pain points, convert paid compute/auth help, and improve Nomad from the results.",
  [int]$Cycles = 0,
  [int]$IntervalSeconds = 900,
  [string]$Model = "",
  [int]$OutreachLimit = 10,
  [int]$ServiceLimit = 25,
  [int]$MaxTokens = 80,
  [string]$Query = "",
  [int]$Port = 8787,
  [string]$PublicUrl = "",
  [string]$TunnelToken = "",
  [string]$CloudflaredPath = ""
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      return
    }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
      $name = $matches[1]
      $value = $matches[2].Trim()
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      if (-not (Get-Item "Env:$name" -ErrorAction SilentlyContinue)) {
        Set-Item "Env:$name" $value
      }
    }
  }
}

$cloudflared = if ($CloudflaredPath) { $CloudflaredPath } else { Join-Path $root "tools\\cloudflared\\cloudflared.exe" }
if (-not (Test-Path $cloudflared)) {
  throw "cloudflared.exe not found at $cloudflared"
}

if (-not $TunnelToken -and $env:NOMAD_CLOUDFLARE_TUNNEL_TOKEN) {
  $TunnelToken = $env:NOMAD_CLOUDFLARE_TUNNEL_TOKEN
}
if (-not $PublicUrl -and $env:NOMAD_PUBLIC_API_URL) {
  $PublicUrl = $env:NOMAD_PUBLIC_API_URL
}
$useNamedTunnel = -not [string]::IsNullOrWhiteSpace($TunnelToken)
if ($useNamedTunnel -and [string]::IsNullOrWhiteSpace($PublicUrl)) {
  throw "Named tunnel mode requires -PublicUrl or NOMAD_PUBLIC_API_URL with the stable Cloudflare hostname."
}

if (-not $Model) {
  $Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "qwen2.5:0.5b-instruct" }
}

$runtimeDir = Join-Path $root "tools\\nomad-live"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$pidFiles = @(
  (Join-Path $runtimeDir "autopilot.pid"),
  (Join-Path $runtimeDir "cloudflared.pid")
)
foreach ($pidFile in $pidFiles) {
  if (Test-Path $pidFile) {
    $oldPid = (Get-Content $pidFile -Raw).Trim()
    if ($oldPid) {
      Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
  }
}

if ($useNamedTunnel) {
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Named tunnel ingress usually targets a fixed local port, so stop the old process or pass the configured port."
  }
} else {
  while (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    $Port += 1
  }
}

$cloudOut = Join-Path $runtimeDir "cloudflared.out.log"
$cloudErr = Join-Path $runtimeDir "cloudflared.err.log"
$autopilotOut = Join-Path $runtimeDir "autopilot.out.log"
$autopilotErr = Join-Path $runtimeDir "autopilot.err.log"
$publicUrlFile = Join-Path $runtimeDir "public-url.txt"
$portFile = Join-Path $runtimeDir "port.txt"
$tunnelModeFile = Join-Path $runtimeDir "tunnel-mode.txt"

Remove-Item -LiteralPath $cloudOut, $cloudErr, $autopilotOut, $autopilotErr, $publicUrlFile, $portFile, $tunnelModeFile -Force -ErrorAction SilentlyContinue

if ($useNamedTunnel) {
  $publicUrl = $PublicUrl.Trim().TrimEnd("/")
  $cloudProc = Start-Process -FilePath $cloudflared -ArgumentList @("tunnel", "--no-autoupdate", "run", "--token", $TunnelToken) -RedirectStandardOutput $cloudOut -RedirectStandardError $cloudErr -PassThru -WindowStyle Hidden
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if ($cloudProc.HasExited) {
      throw "cloudflared named tunnel exited early with code $($cloudProc.ExitCode). Check $cloudErr"
    }
  }
  Set-Content -Path $tunnelModeFile -Value "cloudflare_named_tunnel" -Encoding ASCII
} else {
  $cloudProc = Start-Process -FilePath $cloudflared -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate") -RedirectStandardOutput $cloudOut -RedirectStandardError $cloudErr -PassThru -WindowStyle Hidden

  $publicUrl = ""
  for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 1
    $combined = ""
    if (Test-Path $cloudOut) { $combined += (Get-Content -Raw $cloudOut -ErrorAction SilentlyContinue) }
    if (Test-Path $cloudErr) { $combined += "`n" + (Get-Content -Raw $cloudErr -ErrorAction SilentlyContinue) }
    if ($combined -match 'https://[-a-z0-9]+\.trycloudflare\.com') {
      $publicUrl = $matches[0]
      break
    }
    if ($cloudProc.HasExited) {
      throw "cloudflared quick tunnel exited early with code $($cloudProc.ExitCode)"
    }
  }

  if (-not $publicUrl) {
    throw "Timed out while waiting for a Cloudflare public URL."
  }
  Set-Content -Path $tunnelModeFile -Value "cloudflare_quick_tunnel" -Encoding ASCII
}

Set-Content -Path $publicUrlFile -Value $publicUrl -Encoding ASCII
Set-Content -Path $portFile -Value $Port -Encoding ASCII
Set-Content -Path (Join-Path $runtimeDir "cloudflared.pid") -Value $cloudProc.Id -Encoding ASCII

$python = (Get-Command python).Source
$env:OLLAMA_API_BASE = if ($env:OLLAMA_API_BASE) { $env:OLLAMA_API_BASE } else { "http://127.0.0.1:11434" }
$env:OLLAMA_MODEL = $Model
$env:NOMAD_HOSTED_BRAIN_MODE = if ($env:NOMAD_HOSTED_BRAIN_MODE) { $env:NOMAD_HOSTED_BRAIN_MODE } else { "auto" }
Remove-Item Env:NOMAD_ALLOW_HOSTED_BRAINS -ErrorAction SilentlyContinue
$env:NOMAD_OLLAMA_MAX_TOKENS = [string]$MaxTokens
$env:NOMAD_SELF_IMPROVE_MAX_TOKENS = [string]$MaxTokens
$env:NOMAD_OLLAMA_TIMEOUT_SECONDS = if ($env:NOMAD_OLLAMA_TIMEOUT_SECONDS) { $env:NOMAD_OLLAMA_TIMEOUT_SECONDS } else { "15" }
$env:NOMAD_API_HOST = "127.0.0.1"
$env:NOMAD_API_PORT = [string]$Port
$env:NOMAD_PUBLIC_API_URL = $publicUrl
$env:NOMAD_LEAD_FOCUS = if ($env:NOMAD_LEAD_FOCUS) { $env:NOMAD_LEAD_FOCUS } else { "compute_auth" }
$env:NOMAD_OUTREACH_SERVICE_TYPE = if ($env:NOMAD_OUTREACH_SERVICE_TYPE) { $env:NOMAD_OUTREACH_SERVICE_TYPE } else { "compute_auth" }

$arguments = @(
  "main.py",
  "--cli",
  "autopilot",
  "--cycles", [string]$Cycles,
  "--interval", [string]$IntervalSeconds,
  "--outreach-limit", [string]$OutreachLimit,
  "--service-limit", [string]$ServiceLimit,
  "--serve-api",
  "--send-outreach"
)
if ($Query) {
  $arguments += @("--query", $Query)
}
if ($Objective) {
  $arguments += $Objective
}

$autoProc = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -RedirectStandardOutput $autopilotOut -RedirectStandardError $autopilotErr -PassThru -WindowStyle Hidden

Set-Content -Path (Join-Path $runtimeDir "autopilot.pid") -Value $autoProc.Id -Encoding ASCII

Start-Sleep -Seconds 8

$healthOk = $false
$cardOk = $false
try {
  $health = Invoke-WebRequest -Uri "$publicUrl/health" -UseBasicParsing -TimeoutSec 20
  $healthOk = ($health.StatusCode -eq 200)
} catch {
}
try {
  $card = Invoke-WebRequest -Uri "$publicUrl/.well-known/agent-card.json" -UseBasicParsing -TimeoutSec 20
  $cardOk = ($card.StatusCode -eq 200)
} catch {
}

Write-Output "PUBLIC_URL=$publicUrl"
Write-Output "TUNNEL_MODE=$((Get-Content $tunnelModeFile -Raw).Trim())"
Write-Output "PORT=$Port"
Write-Output "CLOUDFLARED_PID=$($cloudProc.Id)"
Write-Output "AUTOPILOT_PID=$($autoProc.Id)"
Write-Output "HEALTH_OK=$healthOk"
Write-Output "AGENT_CARD_OK=$cardOk"
Write-Output "RUNTIME_DIR=$runtimeDir"
