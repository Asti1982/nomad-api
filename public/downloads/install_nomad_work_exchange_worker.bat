@echo off
setlocal EnableDelayedExpansion

set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set OBLIGATION_ID=%2
if "%OBLIGATION_ID%"=="" (
  echo Enter the obligation_id from your Nomad free-solution receipt.
  set /p OBLIGATION_ID=obligation_id: 
)
if "%OBLIGATION_ID%"=="" (
  echo Missing obligation_id. Nothing started.
  exit /b 1
)

set INSTALL_DIR=%USERPROFILE%\NomadWorkExchangeWorker
set WORKER_URL=%BASE_URL%/downloads/nomad_work_exchange_worker.py
set WORKER_FILE=%INSTALL_DIR%\nomad_work_exchange_worker.py
set RUN_FILE=%INSTALL_DIR%\run_nomad_work_exchange_worker.bat

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

echo Downloading Nomad Work Exchange worker from %WORKER_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%WORKER_URL%' -OutFile '%WORKER_FILE%'"
if errorlevel 1 (
  echo Download failed.
  exit /b 1
)

(
echo @echo off
echo setlocal
echo set BASE_URL=%%1
echo if "%%BASE_URL%%"=="" set BASE_URL=%BASE_URL%
echo set OBLIGATION_ID=%%2
echo if "%%OBLIGATION_ID%%"=="" set OBLIGATION_ID=%OBLIGATION_ID%
echo cd /d "%INSTALL_DIR%"
echo python -u "%WORKER_FILE%" --base-url "%%BASE_URL%%" --obligation-id "%%OBLIGATION_ID%%" --loop --cycles 0 --interval 45
) > "%RUN_FILE%"

echo.
echo Installed to: %INSTALL_DIR%
echo Run command:
echo "%RUN_FILE%" "%BASE_URL%" "%OBLIGATION_ID%"
echo.
echo Starting visible worker. It will stop automatically when the balance reaches zero.
start "Nomad Work Exchange Worker" cmd /k ""%RUN_FILE%" "%BASE_URL%" "%OBLIGATION_ID%""
exit /b 0
