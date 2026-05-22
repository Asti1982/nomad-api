param(
  [string]$BaseUrl = "https://www.syndiode.com",
  [string]$AgentId = "edge.external.sebastian-retention-001",
  [string]$OutFile = "C:\tmp\nomad_external_worker_heartbeat.json"
)

$ErrorActionPreference = "Stop"

$root = $BaseUrl.TrimEnd("/")
$query = @{
  agent_id = $AgentId
  runtime = "windows-edge-external"
  capabilities = "transition_worker,verifier,http_json,get_only,retention_heartbeat"
  known_objectives = "settlement_capacity_builder,proof_pressure_engine,protocol_drift_scan"
  objective = "settlement_capacity_builder"
  source_tag = "external_provider"
}

$pairs = foreach ($item in $query.GetEnumerator()) {
  "{0}={1}" -f [uri]::EscapeDataString($item.Key), [uri]::EscapeDataString([string]$item.Value)
}
$leaseUrl = "$root/swarm/workers/lease-get?$($pairs -join '&')"

$lease = Invoke-RestMethod -Method Get -Uri $leaseUrl -TimeoutSec 25

$sample = $null
try {
  $sample = Invoke-RestMethod -Method Post -Uri "$root/swarm/retention-evidence/sample" `
    -Body (@{ source = "windows_edge_external_worker_heartbeat"; agent_id = $AgentId } | ConvertTo-Json -Depth 6) `
    -ContentType "application/json" -TimeoutSec 25
} catch {
  $sample = @{ ok = $false; error = "retention_sample_failed"; message = $_.Exception.Message }
}

$out = @{
  ok = $true
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  base_url = $root
  agent_id = $AgentId
  lease_status = $lease.ok
  lease_id = $lease.lease_id
  retention_sample_ok = $sample.ok
}

$dir = Split-Path -Parent $OutFile
if ($dir) {
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$out | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $OutFile
$out | ConvertTo-Json -Depth 8
