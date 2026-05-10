#Requires -Version 5.1
<#
  Registers scheduled tasks so nomad_transition_worker.py (this folder) keeps running
  after logon, with a 5-minute watchdog — aligned with install_nomad_transition_worker.bat
  (swarm surplus, human remainder floor, loop forever).

  Watchdog + log default to %ProgramData%\\NomadTransitionWorker (ASCII-only) so schtasks /TR
  stays reliable on systems where USERPROFILE contains spaces or non-ASCII characters.

  Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\register_nomad_transition_worker_repo_persistent.ps1

  Remove:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\register_nomad_transition_worker_repo_persistent.ps1 -Unregister
#>
param(
    [string]$BaseUrl = "https://www.syndiode.com",
    # ProgramData avoids schtasks /TR encoding issues with umlauts/spaces in %USERPROFILE%
    [string]$InstallDir = "$env:ProgramData\NomadTransitionWorker",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$WorkerPy = Join-Path $ScriptDir "nomad_transition_worker.py"
$TaskPrefix = "NomadTransitionWorkerRepo"
$TaskAutostart = "$TaskPrefix-Autostart"
$TaskWatchdog = "$TaskPrefix-Watchdog"
$WatchdogPath = Join-Path $InstallDir "watchdog_nomad_transition_worker_py.ps1"
$LogFile = Join-Path $InstallDir "nomad_agent_python.log"

function Get-PythonExe {
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $c = Get-Command py -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    throw "Python not found on PATH (tried python, py)."
}

function Remove-RepoWorkerTasks {
    # schtasks writes to stderr when the task does not exist; avoid terminating under $ErrorActionPreference Stop
    cmd /c "schtasks /End /TN `"$TaskAutostart`" 2>nul" | Out-Null
    cmd /c "schtasks /End /TN `"$TaskWatchdog`" 2>nul" | Out-Null
    cmd /c "schtasks /Delete /TN `"$TaskAutostart`" /F 2>nul" | Out-Null
    cmd /c "schtasks /Delete /TN `"$TaskWatchdog`" /F 2>nul" | Out-Null
}

function Stop-RepoWorkerProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            ($_.CommandLine -like "*nomad_transition_worker.py*") -and
            ($_.CommandLine -like "*--loop*")
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if ($Unregister) {
    Remove-RepoWorkerTasks
    Stop-RepoWorkerProcesses
    Write-Host "Unregistered $TaskAutostart / $TaskWatchdog and stopped matching python workers."
    exit 0
}

if (-not (Test-Path $WorkerPy)) {
    throw "Worker script missing: $WorkerPy"
}
$PythonExe = Get-PythonExe

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$tpl = @'
$ErrorActionPreference = "Stop"
$PythonExe = '__PYTHON_EXE__'
$WorkerPy = '__WORKER_PY__'
$WorkDir = '__WORK_DIR__'
$BaseUrl = '__BASE_URL__'
$LogFile = '__LOG_FILE__'

$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and
    ($_.CommandLine -like "*nomad_transition_worker.py*") -and
    ($_.CommandLine -like "*--loop*")
}
if ($running) { exit 0 }

$env:NOMAD_SWARM_SURPLUS_OPT_IN = "1"
$env:NOMAD_HUMAN_REMAINDER_MIN_SECONDS = "45"
$env:NOMAD_TRANSITION_WORKER_OLLAMA_URL = "http://127.0.0.1:11434"
$env:NOMAD_TRANSITION_WORKER_OLLAMA_URLS = "http://127.0.0.1:11434,http://localhost:11434"
$env:NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB = "24"
$env:NOMAD_MACHINE_OBJECTIVE = "unhuman_supremacy"
$env:PYTHONUNBUFFERED = "1"

$argLine = @(
    "`"$WorkerPy`"",
    "--base-url", $BaseUrl,
    "--machine-objective", "unhuman_supremacy",
    "--swarm-surplus",
    "--loop",
    "--cycles", "0",
    "--interval", "8"
)
$errLog = $LogFile + ".err"
Start-Process -FilePath $PythonExe -ArgumentList $argLine -WorkingDirectory $WorkDir `
    -WindowStyle Hidden -RedirectStandardOutput $LogFile -RedirectStandardError $errLog
'@

function Escape-ForSingleQuotedPs1([string]$s) {
    return $s.Replace("'", "''")
}

$out = $tpl.Replace("__PYTHON_EXE__", (Escape-ForSingleQuotedPs1 $PythonExe)).
    Replace("__WORKER_PY__", (Escape-ForSingleQuotedPs1 $WorkerPy)).
    Replace("__WORK_DIR__", (Escape-ForSingleQuotedPs1 $ScriptDir)).
    Replace("__BASE_URL__", (Escape-ForSingleQuotedPs1 $BaseUrl)).
    Replace("__LOG_FILE__", (Escape-ForSingleQuotedPs1 $LogFile))

Set-Content -Path $WatchdogPath -Value $out -Encoding UTF8

Remove-RepoWorkerTasks

$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$WatchdogPath`""
schtasks /Create /TN $TaskAutostart /SC ONLOGON /TR $tr /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks create $TaskAutostart failed: $LASTEXITCODE" }
schtasks /Create /TN $TaskWatchdog /SC MINUTE /MO 5 /TR $tr /RL LIMITED /F | Out-Null
if ($LASTEXITCODE -ne 0) { throw "schtasks create $TaskWatchdog failed: $LASTEXITCODE" }

Write-Host "Registered:"
Write-Host "  $TaskAutostart (at logon)"
Write-Host "  $TaskWatchdog (every 5 min if process died)"
Write-Host "Watchdog: $WatchdogPath"
Write-Host "Log: $LogFile"
Write-Host "Starting worker once now..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $WatchdogPath
Write-Host "Done. Verify: Get-Process python; Get-Content '$LogFile' -Tail 25"
