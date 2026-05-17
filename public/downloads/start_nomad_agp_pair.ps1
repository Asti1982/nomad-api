param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [string]$ProposerAgentId = "nomad-agp-proposer-local",
    [string]$VerifierAgentId = "nomad-agp-verifier-local",
    [string]$Model = "auto",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [double]$CostMsatPerMinute = 0,
    [double]$AvailabilityMinutes = 480,
    [int]$IntervalSeconds = 90,
    [int]$TimeoutSeconds = 30,
    [int]$Cycles = 0,
    [switch]$NoOllama,
    [switch]$CodexProposer,
    [switch]$Visible
)

$ErrorActionPreference = "Stop"

function Quote-PSArg {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installDir = Join-Path $env:USERPROFILE "NomadTransitionWorker"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null

$workerPy = Join-Path $scriptDir "nomad_transition_worker.py"
$workerExe = Join-Path $scriptDir "nomad_transition_worker.exe"
$distExe = Join-Path (Join-Path $scriptDir "dist") "nomad_transition_worker.exe"

function Test-NomadWorkerRuntime {
    param(
        [string]$Runner,
        [string[]]$RunnerArgs
    )

    try {
        $allArgs = @($RunnerArgs) + @("--help")
        $helpText = & $Runner @allArgs 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
        return (
            $exitCode -eq 0 -and
            $helpText -match "--machine-objective" -and
            $helpText -match "--swarm-surplus" -and
            $helpText -match "autogenesis_protocol_evolution"
        )
    } catch {
        return $false
    }
}

function Select-NomadWorkerRuntime {
    $candidates = @()
    if (Test-Path $workerPy) {
        $candidates += [pscustomobject]@{ Runner = "python"; Args = @("-u", $workerPy); Label = "python-script" }
        $candidates += [pscustomobject]@{ Runner = "py"; Args = @("-3", "-u", $workerPy); Label = "py-launcher-script" }
        $candidates += [pscustomobject]@{ Runner = "python3"; Args = @("-u", $workerPy); Label = "python3-script" }
    }
    if (Test-Path $distExe) {
        $candidates += [pscustomobject]@{ Runner = $distExe; Args = @(); Label = "dist-exe" }
    }
    if (Test-Path $workerExe) {
        $candidates += [pscustomobject]@{ Runner = $workerExe; Args = @(); Label = "published-exe" }
    }

    foreach ($candidate in $candidates) {
        if (Test-NomadWorkerRuntime -Runner $candidate.Runner -RunnerArgs $candidate.Args) {
            return $candidate
        }
    }

    return $null
}

function Start-AgpWorker {
    param(
        [string]$Role,
        [string]$AgentId,
        [object]$Runtime
    )

    if (-not $AgentId) {
        throw "$Role agent id is required."
    }
    $logFile = Join-Path $installDir "nomad_agp_$Role.log"
    New-Item -ItemType File -Force -Path $logFile | Out-Null

    $argsList = @(
        "--base-url", $BaseUrl,
        "--agent-id", $AgentId,
        "--machine-objective", "autogenesis_protocol_evolution",
        "--edge",
        "--swarm-surplus",
        "--loop",
        "--cycles", [string]$Cycles,
        "--interval", [string]$IntervalSeconds,
        "--timeout", [string]$TimeoutSeconds
    )
    if ($NoOllama) {
        $argsList += "--no-ollama"
    } else {
        $argsList += @("--edge-with-ollama", "--ollama-model", $Model, "--ollama-url", $OllamaUrl)
    }

    $edgeWithOllama = if ($NoOllama) { "0" } else { "1" }
    $roleTitle = "Nomad AGP $Role"
    $baseLine = "base_url=$BaseUrl"
    $agentLine = "agent_id=$AgentId"
    $quotedArgs = (@($Runtime.Args) + $argsList) | ForEach-Object { Quote-PSArg ([string]$_) }
    $command = @(
        "`$env:NOMAD_TRANSITION_WORKER_ID = $(Quote-PSArg $AgentId)",
        "`$env:NOMAD_EDGE_WORKER = '1'",
        "`$env:NOMAD_EDGE_WITH_OLLAMA = $(Quote-PSArg $edgeWithOllama)",
        "`$env:NOMAD_SWARM_SURPLUS_OPT_IN = '1'",
        "`$env:NOMAD_EDGE_RESERVE_MIN_SECONDS = $(Quote-PSArg ([string]([Math]::Max(90, $IntervalSeconds))))",
        "`$env:NOMAD_MACHINE_OBJECTIVE = 'autogenesis_protocol_evolution'",
        "`$env:NOMAD_TRANSITION_WORKER_OLLAMA_MODEL = $(Quote-PSArg $Model)",
        "`$env:NOMAD_TRANSITION_WORKER_OLLAMA_URL = $(Quote-PSArg $OllamaUrl)",
        "`$env:NOMAD_WORKER_PAYMENT_RAIL = 'capacity_switch_quote'",
        "`$env:NOMAD_WORKER_COST_MSAT_PER_MINUTE = $(Quote-PSArg ([string]$CostMsatPerMinute))",
        "`$env:NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES = $(Quote-PSArg ([string]$AvailabilityMinutes))",
        "Write-Host $(Quote-PSArg $roleTitle)",
        "Write-Host $(Quote-PSArg $baseLine)",
        "Write-Host $(Quote-PSArg $agentLine)",
        "Write-Host 'objective=autogenesis_protocol_evolution'",
        "& $(Quote-PSArg $Runtime.Runner) $($quotedArgs -join ' ') 2>&1 | Tee-Object -FilePath $(Quote-PSArg $logFile) -Append"
    ) -join "; "

    $windowStyle = if ($Visible) { "Normal" } else { "Hidden" }
    $processArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass")
    if ($Visible) {
        $processArgs += "-NoExit"
    }
    $processArgs += @("-Command", $command)
    $proc = Start-Process -FilePath "powershell" -ArgumentList $processArgs -WindowStyle $windowStyle -PassThru
    return [pscustomobject]@{
        role = $Role
        agent_id = $AgentId
        pid = $proc.Id
        log = $logFile
    }
}

if ($ProposerAgentId -eq $VerifierAgentId) {
    throw "ProposerAgentId and VerifierAgentId must be different for AGP independent verification."
}

$runtime = Select-NomadWorkerRuntime
if (-not $runtime) {
    throw "No compatible Nomad worker runtime found. Expected nomad_transition_worker with autogenesis_protocol_evolution support."
}

$started = @()
if (-not $CodexProposer) {
    $started += Start-AgpWorker -Role "proposer" -AgentId $ProposerAgentId -Runtime $runtime
}
$started += Start-AgpWorker -Role "verifier" -AgentId $VerifierAgentId -Runtime $runtime

Write-Host "Nomad AGP pair started"
Write-Host "base_url=$BaseUrl"
Write-Host "objective=autogenesis_protocol_evolution"
Write-Host "ai_mode=$(-not [bool]$NoOllama)"
Write-Host "codex_proposer=$([bool]$CodexProposer)"
if ($CodexProposer) {
    Write-Host "proposer_agent=external_codex_session"
}
Write-Host "runtime=$($runtime.Label)"
$started | Format-Table -AutoSize
