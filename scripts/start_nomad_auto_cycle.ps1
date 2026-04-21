param(
  [string]$Objective = "Nomad auto-cycle startup: sell useful agent help, develop Nomad, and help the public AI-agent world through the live edge.",
  [int]$IntervalSeconds = 3600,
  [int]$OutreachLimit = 10,
  [int]$ConversionLimit = 5,
  [int]$DailyLeadTarget = 100,
  [int]$ServiceLimit = 25
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
      return
    }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
      $name = $matches[1]
      $value = $matches[2].Trim()
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      Set-Item "Env:$name" $value
    }
  }
}

if (-not $env:NOMAD_PUBLIC_API_URL) {
  $env:NOMAD_PUBLIC_API_URL = "https://nomad-api-4s84.onrender.com"
}

function Add-NomadGrantAction {
  param([string]$Action)
  $existing = @()
  if ($env:NOMAD_OPERATOR_GRANT_ACTIONS) {
    $existing = $env:NOMAD_OPERATOR_GRANT_ACTIONS -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ }
  }
  if ($existing -notcontains $Action) {
    $existing += $Action
  }
  $env:NOMAD_OPERATOR_GRANT_ACTIONS = ($existing -join ",")
}

$env:NOMAD_AUTOPILOT_A2A_SEND = "true"
$env:NOMAD_AUTOPILOT_SEND_OUTREACH = "true"
$env:NOMAD_AUTOPILOT_INTERVAL_SECONDS = [string]$IntervalSeconds
$env:NOMAD_AUTOPILOT_OUTREACH_LIMIT = [string]$OutreachLimit
$env:NOMAD_AUTOPILOT_CONVERSION_LIMIT = [string]$ConversionLimit
$env:NOMAD_AUTOPILOT_DAILY_LEAD_TARGET = [string]$DailyLeadTarget
$env:NOMAD_AUTOPILOT_SERVICE_LIMIT = [string]$ServiceLimit
$env:NOMAD_OPERATOR_GRANT = if ($env:NOMAD_OPERATOR_GRANT) { $env:NOMAD_OPERATOR_GRANT } else { "product_sales_agent_help_self_development" }
$env:NOMAD_OPERATOR_GRANT_SCOPE = if ($env:NOMAD_OPERATOR_GRANT_SCOPE) { $env:NOMAD_OPERATOR_GRANT_SCOPE } else { "public_agent_help_sales_productization_bounded_development" }
$env:NOMAD_OPERATOR_GRANT_ACTIONS = if ($env:NOMAD_OPERATOR_GRANT_ACTIONS) { $env:NOMAD_OPERATOR_GRANT_ACTIONS } else { "development,self_development,self_improvement,productization,lead_discovery,lead_conversion,machine_outreach,agent_endpoint_contact,human_outreach,public_pr_plan,service_work,code_review_diff_share,render_edge_health,autonomous_continuation" }
Add-NomadGrantAction "human_outreach"
Add-NomadGrantAction "public_pr_plan"
Add-NomadGrantAction "autonomous_continuation"
$env:NOMAD_AUTOPILOT_SERVICE_APPROVAL = if ($env:NOMAD_AUTOPILOT_SERVICE_APPROVAL) { $env:NOMAD_AUTOPILOT_SERVICE_APPROVAL } else { "operator_granted" }
$env:NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD = if ($env:NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD) { $env:NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD } else { "true" }
$env:APPROVE_SELF_DEV = if ($env:APPROVE_SELF_DEV) { $env:APPROVE_SELF_DEV } else { "yes" }
$env:SCOUT_PERMISSION = if ($env:SCOUT_PERMISSION) { $env:SCOUT_PERMISSION } else { "public_github" }
$env:APPROVE_LEAD_HELP = if ($env:APPROVE_LEAD_HELP) { $env:APPROVE_LEAD_HELP } else { "machine_endpoint" }

$runtimeDir = Join-Path $root "tools\nomad-live"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$pidFile = Join-Path $runtimeDir "auto-cycle.pid"
if (Test-Path $pidFile) {
  $oldPid = (Get-Content $pidFile -Raw).Trim()
  if ($oldPid) {
    Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
  }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object {
    $cmd = $_.CommandLine -or ""
    $cmd -like "*main.py*" -and $cmd -like "*--cli*" -and $cmd -like "*autopilot*"
  } |
  ForEach-Object {
    Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue
  }

$outLog = Join-Path $runtimeDir "auto-cycle.out.log"
$errLog = Join-Path $runtimeDir "auto-cycle.err.log"
$statusFile = Join-Path $runtimeDir "auto-cycle-status.json"
Remove-Item -LiteralPath $outLog, $errLog, $statusFile -Force -ErrorAction SilentlyContinue

$python = (Get-Command python).Source
$arguments = @(
  "main.py",
  "--cli",
  "autopilot",
  "--cycles", "0",
  "--interval", [string]$IntervalSeconds,
  "--outreach-limit", [string]$OutreachLimit,
  "--conversion-limit", [string]$ConversionLimit,
  "--daily-lead-target", [string]$DailyLeadTarget,
  "--service-limit", [string]$ServiceLimit,
  "--service-approval", $env:NOMAD_AUTOPILOT_SERVICE_APPROVAL,
  "--send-outreach",
  "--send-a2a",
  "--self-schedule",
  $Objective
)

$proc = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru -WindowStyle Hidden
Set-Content -Path $pidFile -Value $proc.Id -Encoding ASCII

$status = [ordered]@{
  mode = "nomad_auto_cycle_startup"
  started_at = (Get-Date).ToString("o")
  pid = $proc.Id
  public_api_url = $env:NOMAD_PUBLIC_API_URL
  interval_seconds = $IntervalSeconds
  outreach_limit = $OutreachLimit
  conversion_limit = $ConversionLimit
  daily_lead_target = $DailyLeadTarget
  service_limit = $ServiceLimit
  self_schedule = $true
  service_approval = $env:NOMAD_AUTOPILOT_SERVICE_APPROVAL
  grant = $env:NOMAD_OPERATOR_GRANT
  grant_scope = $env:NOMAD_OPERATOR_GRANT_SCOPE
  grant_actions = $env:NOMAD_OPERATOR_GRANT_ACTIONS
  codebuddy_diff_upload = $env:NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD
  out_log = $outLog
  err_log = $errLog
}
$status | ConvertTo-Json -Depth 4 | Set-Content -Path $statusFile -Encoding ASCII

Write-Output "NOMAD_AUTO_CYCLE_PID=$($proc.Id)"
Write-Output "NOMAD_PUBLIC_API_URL=$($env:NOMAD_PUBLIC_API_URL)"
Write-Output "STATUS_FILE=$statusFile"
Write-Output "OUT_LOG=$outLog"
Write-Output "ERR_LOG=$errLog"
