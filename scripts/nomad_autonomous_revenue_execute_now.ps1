param(
    [string]$BaseUrl = "https://www.syndiode.com",
    [switch]$StartLocalWorker
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$env:NOMAD_ALLOW_PAID_MODEL_CALLS = if ($env:NOMAD_ALLOW_PAID_MODEL_CALLS) { $env:NOMAD_ALLOW_PAID_MODEL_CALLS } else { "false" }
$env:NOMAD_ALLOW_GEMINI_SPEND = if ($env:NOMAD_ALLOW_GEMINI_SPEND) { $env:NOMAD_ALLOW_GEMINI_SPEND } else { "false" }
$env:NOMAD_MAX_PAID_PROBE_USD = if ($env:NOMAD_MAX_PAID_PROBE_USD) { $env:NOMAD_MAX_PAID_PROBE_USD } else { "0" }
$env:NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD = if ($env:NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD) { $env:NOMAD_GEMINI_MONTHLY_SPEND_CAP_USD } else { "0" }

function Write-Step($text) {
    Write-Host ""
    Write-Host ("== " + $text)
}

function Try-Json($cmd) {
    try {
        $raw = Invoke-Expression $cmd
        if (-not $raw) { return $null }
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Invoke-WebStatus($url) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 20
        return @{ ok = $true; code = [int]$r.StatusCode }
    } catch {
        $code = 0
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $code = [int]$_.Exception.Response.StatusCode.value__
        }
        return @{ ok = $false; code = $code }
    }
}

function Try-SchemaHint($url) {
    try {
        $j = Invoke-RestMethod -Uri $url -TimeoutSec 20 -Method Get
        if ($null -eq $j) { return "" }
        if ($j.schema) { return [string]$j.schema }
        if ($j.PSObject.Properties["ok"]) { return "ok=" + [string]$j.ok }
        return "json_without_schema"
    } catch {
        return ""
    }
}

Write-Step "Render deploy source check"
$render = Try-Json "python nomad_cli.py render --json 2>&1"
if ($render -and $render.status -and $render.status.verification) {
    $selected = $render.status.verification.selected_service
    $live = $null
    if ($render.status.recent_deploys -and $render.status.recent_deploys.deploys) {
        $live = $render.status.recent_deploys.deploys | Where-Object { $_.status -eq "live" } | Select-Object -First 1
    }
    Write-Host ("service_name=" + $selected.name)
    Write-Host ("service_id=" + $selected.id)
    Write-Host ("repo=" + $selected.repo)
    Write-Host ("branch=" + $selected.branch)
    Write-Host ("url=" + $selected.url)
    if ($live) {
        Write-Host ("live_commit=" + $live.commit_id)
        Write-Host ("live_deploy_status=" + $live.status)
    }
} else {
    Write-Host "render_check=failed_or_unavailable"
}

Write-Step "Public API smoke check (baseline)"
$baseChecks = @(
    "/health",
    "/openapi.json",
    "/.well-known/agent-card.json",
    "/.well-known/nomad-capacity-switch.json",
    "/swarm/capacity-switch"
)
foreach ($path in $baseChecks) {
    $status = Invoke-WebStatus ($BaseUrl.TrimEnd("/") + $path)
    Write-Host ($path + " -> " + $status.code)
}

Write-Step "Revenue-adjacent surfaces (HTTP + schema hint)"
$revPaths = @(
    "/machine-economy",
    "/swarm/worker-market",
    "/swarm/microtask-metrics",
    "/.well-known/nomad-spend-guard.json",
    "/.well-known/nomad-paid-ref-market.json",
    "/.well-known/nomad-paid-ref-selfplay.json",
    "/.well-known/nomad-bounty-hunter.json",
    "/.well-known/nomad-revenue-science.json",
    "/.well-known/nomad-worker-invoice.json"
)
foreach ($path in $revPaths) {
    $u = $BaseUrl.TrimEnd("/") + $path
    $status = Invoke-WebStatus $u
    $hint = ""
    if ($status.code -eq 200) {
        $hint = Try-SchemaHint $u
    }
    if ($hint) {
        Write-Host ($path + " -> " + $status.code + " hint=" + $hint)
    } else {
        Write-Host ($path + " -> " + $status.code)
    }
}

Write-Step "Deploy gate check"
$gateCmd = "python public/downloads/go_no_go_nomad_deploy.py --base-url $BaseUrl"
try {
    $gateRaw = Invoke-Expression $gateCmd
    $gate = $gateRaw | ConvertFrom-Json
    Write-Host ("go=" + [bool]$gate.go)
    if ($gate.checks) {
        $failed = @($gate.checks.PSObject.Properties | Where-Object { -not [bool]$_.Value } | Select-Object -ExpandProperty Name)
        if ($failed.Count -gt 0) {
            Write-Host ("failed_checks=" + ($failed -join ","))
        }
    }
} catch {
    Write-Host "deploy_gate=failed_to_run"
}

Write-Step "Local worker check"
$workers = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine -match "nomad_transition_worker.py"
}
if ($workers) {
    Write-Host ("local_worker_running=true count=" + $workers.Count)
} else {
    Write-Host "local_worker_running=false"
    if ($StartLocalWorker) {
        Write-Host "starting_worker_via_watchdog=true"
        schtasks /Run /TN "NomadTransitionWorkerRepo-Watchdog" 2>$null | Out-Null
        Start-Sleep -Seconds 4
        $workers2 = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.CommandLine -and $_.CommandLine -match "nomad_transition_worker.py"
        }
        Write-Host ("local_worker_running_after_start=" + [bool]$workers2)
    }
}

Write-Step "Revenue autonomy focus"
Write-Host "1) Treat external bounty/GitHub success as orthogonal; Nomad supplies contract surfaces + deploy truth."
Write-Host "2) Never log or commit payout secrets; use host env / vault only."
Write-Host "3) Require go_no_go gate before scaling autonomous economic assumptions."
Write-Host "4) Prefer surfaces with explicit settle/verify semantics for run-rate accounting."
Write-Host "5) Use /swarm/bounty-hunter for authorized paid OSS work; proof first, claim second, payout secrets never in public text."
