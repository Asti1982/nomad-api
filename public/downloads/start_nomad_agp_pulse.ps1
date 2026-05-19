param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [string]$AgentId = "nomad-agp-pulse-local",
    [string]$ProposerAgentId = "nomad-agp-proposer-brain-local",
    [string]$VerifierAgentId = "nomad-agp-verifier-brain-local",
    [int]$IntervalSeconds = 300,
    [int]$MaxPulsesPerDay = 288,
    [int]$MaxMutationsPerDay = 24,
    [int]$MaxModelCallsPerDay = 0,
    [int]$MaxCycles = 1,
    [int]$LeaseSeconds = 600,
    [int]$Cycles = 0,
    [switch]$InstallTask,
    [switch]$RemoveTask,
    [string]$TaskName = "NomadAgpPulse"
)

$ErrorActionPreference = "Stop"

function Invoke-NomadWorkerLease {
    param(
        [string]$Role,
        [string]$WorkerAgentId,
        [int]$Tick
    )

    $uri = ($BaseUrl.TrimEnd("/") + "/swarm/workers/lease")
    $body = [ordered]@{
        agent_id = $WorkerAgentId
        capabilities = @("transition_worker", "agp_$Role", "rspl", "sepl", "receipt_digest_check")
        known_objectives = @("autogenesis_protocol_evolution", "protocol_drift_scan", "proof_pressure_engine")
        proposed_objective = "autogenesis_protocol_evolution"
        lease_seconds = $LeaseSeconds
        source_tag = "nomad.local_free_agp_pulse.$Role"
        tick = $Tick
    } | ConvertTo-Json -Depth 8 -Compress

    return Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body -TimeoutSec 45
}

function Complete-NomadWorkerLease {
    param(
        [object]$Lease,
        [object]$Pulse,
        [string]$Role
    )

    if (-not $Lease -or -not $Lease.lease_id) {
        return
    }

    $uri = ($BaseUrl.TrimEnd("/") + "/swarm/workers/complete")
    $benchmarkScore = 0
    $benchmarkDelta = 0
    if ($Pulse.open_benchmark_suite -and $Pulse.open_benchmark_suite.aggregate) {
        $benchmarkScore = $Pulse.open_benchmark_suite.aggregate.mean_candidate_score
        $benchmarkDelta = $Pulse.open_benchmark_suite.aggregate.mean_effectiveness_delta
    }
    $body = [ordered]@{
        agent_id = $Lease.agent_id
        lease_id = $Lease.lease_id
        report = [ordered]@{
            schema = "nomad.agp_pulse_worker_completion.v1"
            role = $Role
            machine_objective = "autogenesis_protocol_evolution"
            pulse_id = $Pulse.pulse_id
            decision = $Pulse.decision
            proof_digest = $Pulse.pressure_digest
            effectiveness_score = $benchmarkScore
            effectiveness_delta = $benchmarkDelta
            watchdog_decision = if ($Pulse.watchdog) { $Pulse.watchdog.decision } else { "" }
            source = "nomad.local_free_agp_pulse"
        }
    } | ConvertTo-Json -Depth 10 -Compress

    try {
        Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body -TimeoutSec 45 | Out-Null
    } catch {
        Write-Host (@{ generated_at = (Get-Date).ToUniversalTime().ToString("o"); ok = $false; role = $Role; complete_error = $_.Exception.Message } | ConvertTo-Json -Compress)
    }
}

function Invoke-AgpPulse {
    param([int]$Tick)

    $proposerLease = $null
    $verifierLease = $null

    try {
        $proposerLease = Invoke-NomadWorkerLease -Role "proposer" -WorkerAgentId $ProposerAgentId -Tick $Tick
        $verifierLease = Invoke-NomadWorkerLease -Role "verifier" -WorkerAgentId $VerifierAgentId -Tick $Tick
        $uri = ($BaseUrl.TrimEnd("/") + "/swarm/agp/pulse")
        $body = [ordered]@{
            schema = "nomad.agp_pulse_request.v1"
            agent_id = $AgentId
            proposer_agent_id = $ProposerAgentId
            proposer_lease_id = $proposerLease.lease_id
            verifier_agent_id = $VerifierAgentId
            verifier_lease_id = $verifierLease.lease_id
            auto_verifier_lease = $false
            max_pulses_per_day = $MaxPulsesPerDay
            max_mutations_per_day = $MaxMutationsPerDay
            max_model_calls_per_day = $MaxModelCallsPerDay
            max_cycles = $MaxCycles
            min_pressure_score = 0.2
            min_trigger_score = 0.3
            pressure_bucket_minutes = 60
            side_effect_scope = "agp_receipts_and_descriptor_only"
            source_tag = "nomad.local_free_agp_pulse"
            tick = $Tick
        } | ConvertTo-Json -Depth 8 -Compress
        $result = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body -TimeoutSec 90
        Complete-NomadWorkerLease -Lease $proposerLease -Pulse $result -Role "proposer"
        Complete-NomadWorkerLease -Lease $verifierLease -Pulse $result -Role "verifier"
        $summary = [ordered]@{
            generated_at = (Get-Date).ToUniversalTime().ToString("o")
            ok = $result.ok
            accepted = $result.accepted
            decision = $result.decision
            pressure_digest = $result.pressure_digest
            pulse_id = $result.pulse_id
            verifier_lease_id = $verifierLease.lease_id
            watchdog_decision = if ($result.watchdog) { $result.watchdog.decision } else { "" }
        }
        Write-Host ($summary | ConvertTo-Json -Compress)
    } catch {
        Write-Host (@{ generated_at = (Get-Date).ToUniversalTime().ToString("o"); ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)
    }
}

if ($RemoveTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "removed_task=$TaskName"
    exit 0
}

if ($InstallTask) {
    $script = $MyInvocation.MyCommand.Path
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -BaseUrl `"$BaseUrl`" -AgentId `"$AgentId`" -ProposerAgentId `"$ProposerAgentId`" -VerifierAgentId `"$VerifierAgentId`" -IntervalSeconds $IntervalSeconds -MaxPulsesPerDay $MaxPulsesPerDay -MaxMutationsPerDay $MaxMutationsPerDay -MaxModelCallsPerDay $MaxModelCallsPerDay -MaxCycles $MaxCycles -LeaseSeconds $LeaseSeconds"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Nomad free-tier AGP pulse loop" -Force | Out-Null
    Write-Host "installed_task=$TaskName"
    exit 0
}

$tick = 0
while ($true) {
    $tick += 1
    Invoke-AgpPulse -Tick $tick
    if ($Cycles -gt 0 -and $tick -ge $Cycles) {
        break
    }
    Start-Sleep -Seconds ([Math]::Max(60, $IntervalSeconds))
}
