param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [string]$AgentId = "",
    [string]$Model = "auto",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [double]$CostMsatPerMinute = 0,
    [double]$AvailabilityMinutes = 480,
    [int]$IntervalSeconds = 8,
    [int]$Cycles = 0,
    [switch]$Visible,
    [switch]$NoOllama
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installDir = Join-Path $env:USERPROFILE "NomadTransitionWorker"
$logFile = Join-Path $installDir "nomad_worker1.log"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

if (-not $AgentId) {
    $hostId = ($env:COMPUTERNAME -replace "[^A-Za-z0-9_.-]", "_").ToLowerInvariant()
    $AgentId = "nomad-worker1-$hostId"
}

$workerPy = Join-Path $scriptDir "nomad_transition_worker.py"
$workerExe = Join-Path $scriptDir "nomad_transition_worker.exe"
$distExe = Join-Path (Join-Path $scriptDir "dist") "nomad_transition_worker.exe"
if (Test-Path $workerPy) {
    $runner = "python"
    $runnerArgs = @($workerPy)
} elseif (Test-Path $distExe) {
    $runner = $distExe
    $runnerArgs = @()
} elseif (Test-Path $workerExe) {
    $runner = $workerExe
    $runnerArgs = @()
} else {
    throw "nomad_transition_worker.py or nomad_transition_worker.exe not found next to start_nomad_worker1.ps1"
}

$env:NOMAD_TRANSITION_WORKER_ID = $AgentId
$env:NOMAD_TRANSITION_WORKER_OLLAMA_URL = $OllamaUrl
$env:NOMAD_TRANSITION_WORKER_OLLAMA_URLS = "$OllamaUrl,http://localhost:11434"
$env:NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB = "24"
$env:NOMAD_MACHINE_OBJECTIVE = "unhuman_supremacy"
$env:NOMAD_WORKER_PAYMENT_RAIL = "lightning_l402_quote"
$env:NOMAD_WORKER_COST_MSAT_PER_MINUTE = [string]$CostMsatPerMinute
$env:NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES = [string]$AvailabilityMinutes

if (-not $NoOllama) {
    try {
        Invoke-RestMethod -Method Get -Uri "$OllamaUrl/api/tags" -TimeoutSec 4 | Out-Null
    } catch {
        $ollamaExe = Get-Command ollama -ErrorAction SilentlyContinue
        if ($ollamaExe) {
            Start-Process -FilePath $ollamaExe.Source -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
    }
}

$argsList = @(
    "--base-url", $BaseUrl,
    "--agent-id", $AgentId,
    "--machine-objective", "unhuman_supremacy",
    "--loop",
    "--cycles", [string]$Cycles,
    "--interval", [string]$IntervalSeconds
)
if ($NoOllama) {
    $argsList += "--no-ollama"
} elseif ($Model) {
    $argsList += @("--ollama-model", $Model, "--ollama-url", $OllamaUrl)
}

Write-Host "Nomad Worker 1"
Write-Host "base_url=$BaseUrl"
Write-Host "agent_id=$AgentId"
Write-Host "model=$Model"
Write-Host "market_cost_msat_per_minute=$CostMsatPerMinute"
Write-Host "availability_minutes=$AvailabilityMinutes"
Write-Host "log=$logFile"

if ($Visible) {
    & $runner @runnerArgs @argsList 2>&1 | Tee-Object -FilePath $logFile -Append
} else {
    $command = "& `"$runner`" " + (($runnerArgs + $argsList) | ForEach-Object { "`"$_`"" }) -join " "
    $command = "$command 2>&1 | Tee-Object -FilePath `"$logFile`" -Append"
    Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command -WindowStyle Hidden
    Write-Host "started_background=1"
}
