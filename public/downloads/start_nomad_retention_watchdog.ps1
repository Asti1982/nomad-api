param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [int]$MaxActions = 8,
    [string]$LogPath = "$env:ProgramData\NomadRetentionWatchdog\retention-watchdog.jsonl"
)

$ErrorActionPreference = "Stop"

function Write-JsonLine {
    param([object]$Row)
    $dir = Split-Path -Parent $LogPath
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    ($Row | ConvertTo-Json -Depth 20 -Compress) | Add-Content -Path $LogPath -Encoding UTF8
}

$root = $BaseUrl.TrimEnd("/")
$uri = "$root/swarm/retention/watchdog"
$body = @{
    max_actions = $MaxActions
    reactivate_dormant = $true
    dormant_recovery_window_seconds = 7200
    source_tag = "nomad.local_retention_watchdog_ping"
} | ConvertTo-Json -Depth 10

try {
    $result = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body -TimeoutSec 45
    Write-JsonLine @{
        ok = $true
        sampled_at = (Get-Date).ToUniversalTime().ToString("o")
        uri = $uri
        schema = $result.schema
        executed = [bool]$result.executed
        accepted = [bool]$result.accepted
        retention_score_before = $result.retention_score_before
        retention_score_after = $result.retention_score_after
        action_count = @($result.actions).Count
        watchdog_id = $result.watchdog_id
    }
    Write-Host ("retention_watchdog ok executed={0} accepted={1} actions={2} score={3}->{4}" -f $result.executed, $result.accepted, @($result.actions).Count, $result.retention_score_before, $result.retention_score_after)
    exit 0
}
catch {
    Write-JsonLine @{
        ok = $false
        sampled_at = (Get-Date).ToUniversalTime().ToString("o")
        uri = $uri
        error = $_.Exception.Message
    }
    Write-Error $_
    exit 1
}
