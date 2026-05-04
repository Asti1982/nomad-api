@echo off
setlocal

set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
set INSTALL_DIR=%USERPROFILE%\NomadTransitionWorker
set EXE_URL=%BASE_URL%/downloads/nomad_transition_worker.exe
set RUNNER_URL=%BASE_URL%/downloads/run_nomad_transition_worker_exe.bat
set README_URL=%BASE_URL%/downloads/README_NOMAD_TRANSITION_WORKER.md

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
echo Starting worker in background loop...
start "Nomad Transition Worker" "%INSTALL_DIR%\nomad_transition_worker.exe" --base-url %BASE_URL% --loop --cycles 0
echo.
echo Worker started. You can run it manually anytime from:
echo %INSTALL_DIR%\nomad_transition_worker.exe
echo.
exit /b 0
