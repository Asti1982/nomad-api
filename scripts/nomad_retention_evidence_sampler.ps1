param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [string]$Source = "windows-retention-evidence-sampler"
)

$ErrorActionPreference = "Stop"

$base = $BaseUrl.TrimEnd("/")
$body = @{
    source = $Source
    host = $env:COMPUTERNAME
    sampled_at_local = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json -Compress

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "$base/swarm/retention-evidence/sample" `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 30

[pscustomobject]@{
    ok = [bool]$response.ok
    schema = $response.schema
    sample_digest = $response.sample.digest
    sample_count = $response.ledger.window_summary.sample_count
    claim_allowed = $response.ledger.claim_gate.paper_grade_claim_allowed
} | ConvertTo-Json -Compress
