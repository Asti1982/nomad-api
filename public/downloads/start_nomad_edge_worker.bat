@echo off
setlocal
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set SCRIPT_DIR=%~dp0
set COST=%NOMAD_WORKER_COST_MSAT_PER_MINUTE%
if "%COST%"=="" set COST=0
set AVAIL=%NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES%
if "%AVAIL%"=="" set AVAIL=480
set INTERVAL=%NOMAD_EDGE_INTERVAL_SECONDS%
if "%INTERVAL%"=="" set INTERVAL=90
set TIMEOUT=%NOMAD_EDGE_TIMEOUT_SECONDS%
if "%TIMEOUT%"=="" set TIMEOUT=30

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_nomad_edge_worker.ps1" -BaseUrl "%BASE_URL%" -CostMsatPerMinute %COST% -AvailabilityMinutes %AVAIL% -IntervalSeconds %INTERVAL% -TimeoutSeconds %TIMEOUT% -Visible
