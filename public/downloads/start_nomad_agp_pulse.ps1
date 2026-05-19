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
    [int]$Cycles = 0,
    [switch]$InstallTask,
    [switch]$RemoveTask,
    [string]$TaskName = "NomadAgpPulse"
)

$ErrorActionPreference = "Stop"

function Invoke-AgpPulse {
    param([int]$Tick)
    $uri = ($BaseUrl.TrimEnd("/") + "/swarm/agp/pulse")
    $body = [ordered]@{
        schema = "nomad.agp_pulse_request.v1"
        agent_id = $AgentId
        proposer_agent_id = $ProposerAgentId
        verifier_agent_id = $VerifierAgentId
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
    try {
        $result = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body -TimeoutSec 90
        $summary = [ordered]@{
            generated_at = (Get-Date).ToUniversalTime().ToString("o")
            ok = $result.ok
            accepted = $result.accepted
            decision = $result.decision
            pressure_digest = $result.pressure_digest
            pulse_id = $result.pulse_id
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
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -BaseUrl `"$BaseUrl`" -AgentId `"$AgentId`" -ProposerAgentId `"$ProposerAgentId`" -VerifierAgentId `"$VerifierAgentId`" -IntervalSeconds $IntervalSeconds -MaxPulsesPerDay $MaxPulsesPerDay -MaxMutationsPerDay $MaxMutationsPerDay -MaxModelCallsPerDay $MaxModelCallsPerDay -MaxCycles $MaxCycles"
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
