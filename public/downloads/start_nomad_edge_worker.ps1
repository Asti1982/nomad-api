param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [string]$AgentId = "",
    [double]$CostMsatPerMinute = 0,
    [double]$AvailabilityMinutes = 480,
    [int]$IntervalSeconds = 90,
    [int]$TimeoutSeconds = 30,
    [int]$Cycles = 0,
    [switch]$Visible,
    [switch]$WithOllama
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installDir = Join-Path $env:USERPROFILE "NomadTransitionWorker"
$logFile = Join-Path $installDir "nomad_edge_worker.log"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

if (-not $AgentId) {
    $identityPath = Join-Path $installDir "edge_worker_identity.json"
    if (Test-Path $identityPath) {
        try {
            $identity = Get-Content -Raw -Path $identityPath | ConvertFrom-Json
            $AgentId = [string]$identity.agent_id
        } catch {
            $AgentId = ""
        }
    }
    if (-not $AgentId) {
        $bytes = New-Object byte[] 6
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($bytes)
        $rng.Dispose()
        $suffix = -join ($bytes | ForEach-Object { $_.ToString("x2") })
        $AgentId = "nomad.edge.$suffix"
        @{ schema = "nomad.edge_worker_identity.v1"; agent_id = $AgentId } |
            ConvertTo-Json -Depth 4 |
            Set-Content -Encoding UTF8 -Path $identityPath
    }
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
    throw "nomad_transition_worker.py or nomad_transition_worker.exe not found next to start_nomad_edge_worker.ps1"
}

$env:NOMAD_TRANSITION_WORKER_ID = $AgentId
$env:NOMAD_EDGE_WORKER = "1"
$env:NOMAD_SWARM_SURPLUS_OPT_IN = "1"
$env:NOMAD_EDGE_RESERVE_MIN_SECONDS = [string]([Math]::Max(90, $IntervalSeconds))
$env:NOMAD_MACHINE_OBJECTIVE = "unhuman_supremacy"
$env:NOMAD_WORKER_PAYMENT_RAIL = "capacity_switch_quote"
$env:NOMAD_WORKER_COST_MSAT_PER_MINUTE = [string]$CostMsatPerMinute
$env:NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES = [string]$AvailabilityMinutes

$argsList = @(
    "--base-url", $BaseUrl,
    "--agent-id", $AgentId,
    "--machine-objective", "unhuman_supremacy",
    "--edge",
    "--swarm-surplus",
    "--loop",
    "--cycles", [string]$Cycles,
    "--interval", [string]$IntervalSeconds,
    "--timeout", [string]$TimeoutSeconds
)

if ($WithOllama) {
    $argsList += "--edge-with-ollama"
} else {
    $argsList += "--no-ollama"
}

Write-Host "Nomad Edge Worker"
Write-Host "base_url=$BaseUrl"
Write-Host "agent_id=$AgentId"
if ($WithOllama) {
    Write-Host "model=optional"
} else {
    Write-Host "model=none"
}
Write-Host "interval_seconds=$IntervalSeconds"
Write-Host "timeout_seconds=$TimeoutSeconds"
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
