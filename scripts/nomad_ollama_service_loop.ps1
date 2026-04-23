param(
  [string]$Objective = "",
  [int]$Cycles = 0,
  [int]$IntervalSeconds = 900,
  [string]$Model = "",
  [int]$OutreachLimit = 10,
  [int]$ServiceLimit = 25,
  [int]$MaxTokens = 180,
  [switch]$ServeApi,
  [string]$Query = "",
  [switch]$SendOutreach
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

$args = @(
  "main.py",
  "--cli",
  "autopilot",
  "--cycles", [string]$Cycles,
  "--interval", [string]$IntervalSeconds,
  "--outreach-limit", [string]$OutreachLimit,
  "--service-limit", [string]$ServiceLimit
)

if ($Objective) {
  $args += $Objective
}
if ($Query) {
  $args += @("--query", $Query)
}
if ($ServeApi) {
  $args += "--serve-api"
}
if ($SendOutreach) {
  $args += "--send-outreach"
}

python @args
