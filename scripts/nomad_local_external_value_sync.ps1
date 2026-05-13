#Requires -Version 5.1
<#
  Sync the local durable external-value ledger to the public Render projection.

  Render free storage is ephemeral. This machine is the canonical ledger holder;
  the public API is a replayable projection for agents.
#>
param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [switch]$Apply,
    [switch]$Snapshot,
    [switch]$Loop,
    [int]$IntervalSeconds = 900
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

function Invoke-NomadExternalValueSync {
    $args = @("nomad_cli.py", "external-value", "sync-public", "--base-url", $BaseUrl, "--json")
    if ($Apply) { $args += "--apply" }
    if ($Snapshot) { $args += "--snapshot" }

    $raw = & python @args
    if ($LASTEXITCODE -ne 0) {
        throw "external-value sync failed"
    }
    $result = $raw | ConvertFrom-Json
    Write-Host (
        "mode={0} local_events={1} public_before={2} public_after={3} candidates={4} posted={5} lag_after={6}" -f
        $result.mode,
        $result.local_event_tail_count,
        $result.public_event_tail_count,
        $result.final_public_event_tail_count,
        $result.replay_candidate_count,
        $result.posted_count,
        $result.public_projection_lag_after
    )
    if ($result.snapshot -and $result.snapshot.snapshot_path) {
        Write-Host ("snapshot=" + $result.snapshot.snapshot_path)
    }
}

do {
    Invoke-NomadExternalValueSync
    if ($Loop) {
        Start-Sleep -Seconds ([Math]::Max(30, $IntervalSeconds))
    }
} while ($Loop)
