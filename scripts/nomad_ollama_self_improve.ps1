param(
  [string]$Objective = "Use local Ollama to improve Nomad's next autonomous human-in-the-loop agent-service step.",
  [int]$Cycles = 1,
  [int]$IntervalSeconds = 900,
  [string]$Model = "",
  [int]$MaxTokens = 180
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not $Model) {
  $Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "qwen2.5:0.5b-instruct" }
}

$env:OLLAMA_API_BASE = if ($env:OLLAMA_API_BASE) { $env:OLLAMA_API_BASE } else { "http://127.0.0.1:11434" }
$env:OLLAMA_MODEL = $Model
$env:NOMAD_ALLOW_HOSTED_BRAINS = "false"
$env:NOMAD_OLLAMA_SELF_IMPROVE_MODEL = if ($env:NOMAD_OLLAMA_SELF_IMPROVE_MODEL) { $env:NOMAD_OLLAMA_SELF_IMPROVE_MODEL } else { $Model }
$env:NOMAD_OLLAMA_TIMEOUT_SECONDS = if ($env:NOMAD_OLLAMA_TIMEOUT_SECONDS) { $env:NOMAD_OLLAMA_TIMEOUT_SECONDS } else { "15" }
$env:NOMAD_OLLAMA_MAX_TOKENS = [string]$MaxTokens
$env:NOMAD_SELF_IMPROVE_MAX_TOKENS = [string]$MaxTokens

$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

$cycle = 0
while ($Cycles -eq 0 -or $cycle -lt $Cycles) {
  $cycle += 1
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $out = Join-Path $tools "ollama-self-improve-$stamp.json"
  python main.py --json cycle $Objective | Set-Content -Path $out -Encoding UTF8

  $result = Get-Content $out -Raw | ConvertFrom-Json
  $reviews = @($result.brain_reviews)
  $firstReview = if ($reviews.Count -gt 0) { $reviews[0] } else { $null }
  Write-Output "cycle=$cycle"
  Write-Output "file=$out"
  Write-Output "mode=$($result.mode)"
  Write-Output "brain=$($firstReview.name) model=$($firstReview.model) ok=$($firstReview.ok)"
  Write-Output "next_objective=$($result.self_development.next_objective)"

  if ($Cycles -eq 0 -or $cycle -lt $Cycles) {
    Start-Sleep -Seconds $IntervalSeconds
  }
}
