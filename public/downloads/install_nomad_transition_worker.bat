@echo off
setlocal

set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
set INSTALL_DIR=%USERPROFILE%\NomadTransitionWorker
set EXE_URL=%BASE_URL%/downloads/nomad_transition_worker.exe
set RUNNER_URL=%BASE_URL%/downloads/run_nomad_transition_worker_exe.bat
set README_URL=%BASE_URL%/downloads/README_NOMAD_TRANSITION_WORKER.md
set LOG_FILE=%INSTALL_DIR%\worker.log

echo Installing Nomad Transition Worker from %BASE_URL%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%EXE_URL%' -OutFile '%INSTALL_DIR%\nomad_transition_worker.exe'"
if errorlevel 1 (
  echo Failed to download EXE from %EXE_URL%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%RUNNER_URL%' -OutFile '%INSTALL_DIR%\run_nomad_transition_worker_exe.bat'" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%README_URL%' -OutFile '%INSTALL_DIR%\README_NOMAD_TRANSITION_WORKER.md'" >nul 2>&1

echo.
echo Installed to: %INSTALL_DIR%
echo Checking local Ollama models...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5; if ($r.models) { $r.models | ForEach-Object { $_.name } }" 2>nul
if errorlevel 1 (
  echo Ollama not reachable at 127.0.0.1:11434 - worker will still run.
)
echo Starting worker loop with auto-local-model selection...
echo Log file: %LOG_FILE%
start "Nomad Transition Worker" cmd /k ""%INSTALL_DIR%\nomad_transition_worker.exe" --base-url %BASE_URL% --machine-objective unhuman_supremacy --loop --cycles 0 >> "%LOG_FILE%" 2>&1"
echo.
echo Worker started. You can run it manually anytime from:
echo %INSTALL_DIR%\nomad_transition_worker.exe --base-url %BASE_URL% --machine-objective unhuman_supremacy --loop --cycles 0
echo.
exit /b 0
