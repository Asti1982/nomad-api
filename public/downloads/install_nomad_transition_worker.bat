@echo off
setlocal EnableDelayedExpansion

set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
set INSTALL_DIR=%USERPROFILE%\NomadTransitionWorker
set EXE_URL=%BASE_URL%/downloads/nomad_transition_worker.exe
set RUNNER_URL=%BASE_URL%/downloads/run_nomad_transition_worker_exe.bat
set README_URL=%BASE_URL%/downloads/README_NOMAD_TRANSITION_WORKER.md
set LOG_FILE=%INSTALL_DIR%\nomad_agent.log
set WATCHDOG_PS1=%INSTALL_DIR%\start_nomad_transition_worker.ps1
set OLLAMA_URL=http://127.0.0.1:11434
set OLLAMA_MODEL=llama3.2:latest

set AGENT_ALIAS=%INSTALL_DIR%\nomad_agent.bat
set AGENT_VISIBLE_ALIAS=%INSTALL_DIR%\nomad_agent_visible.bat
set AGENT_STOP_ALIAS=%INSTALL_DIR%\nomad_agent_stop.bat

echo Installing Nomad Agent from %BASE_URL%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%EXE_URL%' -OutFile '%INSTALL_DIR%\nomad_transition_worker.exe'"
if errorlevel 1 (
  echo Failed to download EXE from %EXE_URL%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%RUNNER_URL%' -OutFile '%INSTALL_DIR%\run_nomad_transition_worker_exe.bat'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%README_URL%' -OutFile '%INSTALL_DIR%\README_NOMAD_TRANSITION_WORKER.md'" >nul 2>&1

echo.
echo Preparing local Ollama runtime...
call :spinner 2 "Checking local runtime"
call :ensure_ollama
if errorlevel 1 (
  echo Ollama auto-setup failed. Worker will still start without guaranteed local LLM.
)
call :pick_ollama_model

echo Priming local Ollama model (%OLLAMA_MODEL%)...
call :spinner 2 "Selecting and pulling model"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Method Post -Uri '%OLLAMA_URL%/api/pull' -Body (@{ model='%OLLAMA_MODEL%'; stream=$false } | ConvertTo-Json) -ContentType 'application/json' -TimeoutSec 600 | Out-Null } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo Could not pre-pull %OLLAMA_MODEL%. Auto-model fallback will still try available local models.
)

echo Installed to: %INSTALL_DIR%
echo Checking local Ollama models...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = Invoke-RestMethod -Method Get -Uri '%OLLAMA_URL%/api/tags' -TimeoutSec 5; if ($r.models) { $r.models | ForEach-Object { $_.name } }" 2>nul
if errorlevel 1 (
  echo Ollama not reachable at %OLLAMA_URL% - worker will still run.
)
echo Preparing Nomad Agent launchers...
call :write_aliases
echo Starting Nomad Agent (visible PowerShell + live JSON output)...
echo Log file: %LOG_FILE%
call :write_watchdog
call :register_watchdog_tasks
start "Nomad_Agent_Live" cmd /k "cd /d \"%INSTALL_DIR%\" && set NOMAD_TRANSITION_WORKER_OLLAMA_URL=%OLLAMA_URL% && set NOMAD_TRANSITION_WORKER_OLLAMA_URLS=%OLLAMA_URL%,http://localhost:11434 && set NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB=24 && set NOMAD_MACHINE_OBJECTIVE=unhuman_supremacy && \"%INSTALL_DIR%\nomad_transition_worker.exe\" --base-url %BASE_URL% --machine-objective unhuman_supremacy --loop --cycles 0 --interval 8 >> \"%LOG_FILE%\" 2>&1"
echo.
echo Nomad Agent started.
echo Visible launcher: %AGENT_VISIBLE_ALIAS%
echo Background launcher: %AGENT_ALIAS%
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
echo set OLLAMA_URL=%OLLAMA_URL%
echo set LOG_FILE=%LOG_FILE%
echo cd /d "%INSTALL_DIR%"
echo set NOMAD_TRANSITION_WORKER_OLLAMA_URL=%%OLLAMA_URL%%
echo set NOMAD_TRANSITION_WORKER_OLLAMA_URLS=%%OLLAMA_URL%%,http://localhost:11434
echo set NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB=24
echo set NOMAD_MACHINE_OBJECTIVE=unhuman_supremacy
echo start "nomad_agent" /min "%INSTALL_DIR%\nomad_transition_worker.exe" --base-url %%BASE_URL%% --machine-objective unhuman_supremacy --loop --cycles 0 --interval 8 ^>^> "%%LOG_FILE%%" 2^>^&1
) > "%AGENT_ALIAS%"
(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo set OLLAMA_URL=%OLLAMA_URL%
echo set LOG_FILE=%LOG_FILE%
echo cd /d "%INSTALL_DIR%"
echo powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command "$env:NOMAD_TRANSITION_WORKER_OLLAMA_URL='%%OLLAMA_URL%%'; $env:NOMAD_TRANSITION_WORKER_OLLAMA_URLS='%%OLLAMA_URL%%,http://localhost:11434'; $env:NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB='24'; $env:NOMAD_MACHINE_OBJECTIVE='unhuman_supremacy'; .\nomad_transition_worker.exe --base-url '%%BASE_URL%%' --machine-objective unhuman_supremacy --loop --cycles 0 --interval 8 2^>^&1 ^| Tee-Object -FilePath '%%LOG_FILE%%' -Append"
) > "%AGENT_VISIBLE_ALIAS%"
(
echo @echo off
echo taskkill /IM nomad_transition_worker.exe /F ^>nul 2^>^&1
echo schtasks /End /TN "NomadAgent-Autostart" ^>nul 2^>^&1
echo schtasks /End /TN "NomadAgent-Watchdog" ^>nul 2^>^&1
echo echo Nomad Agent processes stopped.
) > "%AGENT_STOP_ALIAS%"
exit /b 0

:write_watchdog
(
echo param^(
echo     [string]$BaseUrl = "https://syndiode.com",
echo     [string]$InstallDir = "$env:USERPROFILE\NomadTransitionWorker",
echo     [string]$LogFile = "$env:USERPROFILE\NomadTransitionWorker\nomad_agent.log",
echo     [string]$OllamaUrl = "http://127.0.0.1:11434"
echo ^)
echo $exe = Join-Path $InstallDir "nomad_transition_worker.exe"
echo if ^(-not ^(Test-Path $exe^)^) { exit 1 }
echo $already = Get-CimInstance Win32_Process ^| Where-Object { $_.Name -eq "nomad_transition_worker.exe" -and $_.CommandLine -match "unhuman_supremacy" }
echo if ^($already^) { exit 0 }
echo $env:NOMAD_TRANSITION_WORKER_OLLAMA_URL = $OllamaUrl
echo $env:NOMAD_TRANSITION_WORKER_OLLAMA_URLS = "$OllamaUrl,http://localhost:11434"
echo $env:NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB = "24"
echo $env:NOMAD_MACHINE_OBJECTIVE = "unhuman_supremacy"
echo Start-Process -FilePath $exe -ArgumentList "--base-url", $BaseUrl, "--machine-objective", "unhuman_supremacy", "--loop", "--cycles", "0", "--interval", "8" -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -WindowStyle Hidden
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
timeout /t 3 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Method Get -Uri '%OLLAMA_URL%/api/tags' -TimeoutSec 8 | Out-Null } catch { exit 1 }" >nul 2>&1
if not %errorlevel%==0 (
  echo Ollama process is not reachable yet.
  exit /b 1
)
exit /b 0
