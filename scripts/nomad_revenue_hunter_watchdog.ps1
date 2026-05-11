#Requires -Version 5.1
<#
  Read-only GitHub status for focused PR/issue (no comments, no claims, no payout data).
  Optional: record Nomad external-value stage when NOMAD_WATCHDOG_RECORD=1 and you pass --record-stage.

  Defaults target Rustchain PR #4542 and bounty issue #2819 (override via env).

  Env:
    NOMAD_WATCHDOG_PR_REPO   (default: Scottcjn/Rustchain)
    NOMAD_WATCHDOG_PR        (default: 4542)
    NOMAD_WATCHDOG_ISSUE_REPO (default: Scottcjn/rustchain-bounties)
    NOMAD_WATCHDOG_ISSUE     (default: 2819)
    NOMAD_WATCHDOG_RECORD    (set to 1 to call nomad_cli external-value record — requires human go)
#>
param(
    [string]$RecordStage = "",
    [string]$AgentId = "nomad.watchdog.local",
    [string]$ExternalPrId = "",
    [string]$ExternalIssueId = ""
)

$ErrorActionPreference = "Stop"

$prRepo = if ($env:NOMAD_WATCHDOG_PR_REPO) { $env:NOMAD_WATCHDOG_PR_REPO } else { "Scottcjn/Rustchain" }
$prNum = if ($env:NOMAD_WATCHDOG_PR) { $env:NOMAD_WATCHDOG_PR } else { "4542" }
$issueRepo = if ($env:NOMAD_WATCHDOG_ISSUE_REPO) { $env:NOMAD_WATCHDOG_ISSUE_REPO } else { "Scottcjn/rustchain-bounties" }
$issueNum = if ($env:NOMAD_WATCHDOG_ISSUE) { $env:NOMAD_WATCHDOG_ISSUE } else { "2819" }

function Gh-Json($args) {
    $o = & gh @args 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return $o | ConvertFrom-Json
}

Write-Host "== Watchdog (read-only)"
Write-Host "PR $prRepo#$prNum"
$pr = Gh-Json @("pr", "view", $prNum, "-R", $prRepo, "--json", "state,title,url,mergeable,reviewDecision,isDraft,mergedAt,closedAt")
if ($pr) {
    Write-Host ("pr_state=" + $pr.state + " mergeable=" + $pr.mergeable + " reviewDecision=" + $pr.reviewDecision + " draft=" + $pr.isDraft)
    Write-Host ("pr_url=" + $pr.url)
} else {
    Write-Host "pr_fetch=failed (install gh and auth: gh auth login)"
}

Write-Host ""
Write-Host "Issue $issueRepo#$issueNum"
$iss = Gh-Json @("issue", "view", $issueNum, "-R", $issueRepo, "--json", "state,title,url,closedAt")
if ($iss) {
    Write-Host ("issue_state=" + $iss.state)
    Write-Host ("issue_url=" + $iss.url)
} else {
    Write-Host "issue_fetch=failed"
}

if ($env:NOMAD_WATCHDOG_RECORD -eq "1" -and $RecordStage) {
    $root = Resolve-Path (Join-Path $PSScriptRoot "..")
    Set-Location $root
    $ePr = if ($ExternalPrId) { $ExternalPrId } else { "gh_pr:$prRepo#$prNum" }
    $eIss = if ($ExternalIssueId) { $ExternalIssueId } else { "gh_issue:$issueRepo#$issueNum" }
    Write-Host ""
    Write-Host "== Recording external-value (operator responsibility)"
    python nomad_cli.py external-value record --json `
        --agent-id $AgentId --external-id $ePr --stage $RecordStage `
        --work-url ($pr.url) --proof-digest "watchdog" --verifier-trace-digest "watchdog"
}
