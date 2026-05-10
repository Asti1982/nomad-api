#Requires -Version 5.1
<#
.SYNOPSIS
  Diagnose OpenClaw + local Ollama on Windows (Nomad helper, not part of OpenClaw itself).

.DESCRIPTION
  - Checks Ollama HTTP API (default http://127.0.0.1:11434)
  - Runs OpenClaw health/status JSON probes (same as nomad_openclaw_adapter.py)
  - Prints next commands (onboard, doctor) with links to upstream docs

  OpenClaw docs: use native Ollama baseUrl WITHOUT /v1 (breaks tool calling).
  See: https://github.com/openclaw/openclaw/blob/main/docs/providers/ollama.md

.PARAMETER OllamaUrl
  Ollama API root, e.g. http://127.0.0.1:11434

.PARAMETER RunDoctorFix
  If set, runs: openclaw doctor --fix (rewrites legacy auth profiles; backup first).

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose_openclaw_ollama_windows.ps1
#>
param(
  [string]$OllamaUrl = "http://127.0.0.1:11434",
  [switch]$RunDoctorFix
)

$ErrorActionPreference = "Continue"

function Write-Section([string]$t) {
  Write-Host ""
  Write-Host "=== $t ===" -ForegroundColor Cyan
}

Write-Section "Ollama API"
$tagsUrl = ($OllamaUrl.TrimEnd("/")) + "/api/tags"
try {
  $tags = Invoke-RestMethod -Method Get -Uri $tagsUrl -TimeoutSec 6
  $names = @()
  if ($tags.models) { $names = @($tags.models | ForEach-Object { $_.name }) }
  Write-Host "OK: Ollama reachable at $tagsUrl" -ForegroundColor Green
  Write-Host ("Installed models (first 12): " + (($names | Select-Object -First 12) -join ", "))
  if ($names.Count -eq 0) {
    Write-Host "WARN: No models listed. Run: ollama pull llama3.2:1b   (or gemma4, etc.)" -ForegroundColor Yellow
  }
}
catch {
  Write-Host "FAIL: Cannot reach Ollama at $tagsUrl" -ForegroundColor Red
  Write-Host $_.Exception.Message
  Write-Host "Fix: start Ollama (ollama serve / Ollama app), or set -OllamaUrl to your host." -ForegroundColor Yellow
}

Write-Section "OpenClaw CLI"
$oc = Get-Command openclaw -ErrorAction SilentlyContinue
if (-not $oc) {
  Write-Host "FAIL: 'openclaw' not in PATH. Install OpenClaw, then reopen the terminal." -ForegroundColor Red
  exit 1
}
Write-Host ("OK: openclaw at " + $oc.Source) -ForegroundColor Green
try {
  & openclaw --version 2>&1 | ForEach-Object { Write-Host $_ }
}
catch { }

Write-Section "OpenClaw health / status (JSON)"
try {
  $h = & openclaw health --json --timeout 15000 2>&1
  Write-Host $h
  $joined = if ($h -is [array]) { $h -join "`n" } else { "$h" }
  if ($joined -match "ECONNREFUSED|1006 abnormal closure|gateway closed") {
    Write-Host "HINT: Gateway not listening — try: openclaw gateway start   (then re-run health)" -ForegroundColor Yellow
  }
}
catch { Write-Host "openclaw health failed: $($_.Exception.Message)" -ForegroundColor Yellow }

try {
  $s = & openclaw status --json --timeout 15000 2>&1
  Write-Host $s
}
catch { Write-Host "openclaw status failed: $($_.Exception.Message)" -ForegroundColor Yellow }

Write-Section "Control UI / Unauthorized (e.g. http://127.0.0.1:18791/)"
Write-Host "If the browser shows Unauthorized: open the Control UI from the same machine after"
Write-Host "`openclaw gateway` (or onboarding) printed a token URL, or configure gateway auth per"
Write-Host "https://docs.openclaw.ai/gateway/configuration-reference"
Write-Host ""

Write-Section "Recommended repair path (upstream)"
Write-Host "1) Interactive onboarding (pick Ollama):"
Write-Host "     openclaw onboard"
Write-Host ""
Write-Host "2) Non-interactive Ollama onboard (adjust model):"
Write-Host "     openclaw onboard --non-interactive --auth-choice ollama --accept-risk"
Write-Host "     openclaw onboard --non-interactive --auth-choice ollama --custom-base-url `"http://127.0.0.1:11434`" --custom-model-id `"llama3.2:1b`" --accept-risk"
Write-Host ""
Write-Host "3) List Ollama models OpenClaw sees:"
Write-Host "     openclaw models list --provider ollama"
Write-Host ""
Write-Host "4) Config schema (validate keys):"
Write-Host "     openclaw config schema"
Write-Host ""

if ($RunDoctorFix) {
  Write-Section "openclaw doctor --fix"
  & openclaw doctor --fix
}
else {
  Write-Host "Optional: openclaw doctor --fix   (migrates legacy auth profiles; use -RunDoctorFix on this script)" -ForegroundColor DarkGray
}

Write-Section "Nomad bridge (after OpenClaw works)"
Write-Host "python nomad_openclaw_adapter.py --base-url https://www.syndiode.com --loop --cycles 0 --interval 12"
Write-Host "Optional idle swarm: add --idle-earn"
Write-Host ""
exit 0
