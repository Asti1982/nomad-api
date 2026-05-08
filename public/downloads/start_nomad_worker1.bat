@echo off
setlocal
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set SCRIPT_DIR=%~dp0
set MODEL=%NOMAD_TRANSITION_WORKER_OLLAMA_MODEL%
if "%MODEL%"=="" set MODEL=auto
set OLLAMA_URL=%NOMAD_TRANSITION_WORKER_OLLAMA_URL%
if "%OLLAMA_URL%"=="" set OLLAMA_URL=http://127.0.0.1:11434
set COST=%NOMAD_WORKER_COST_MSAT_PER_MINUTE%
if "%COST%"=="" set COST=0
set AVAIL=%NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES%
if "%AVAIL%"=="" set AVAIL=480

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_nomad_worker1.ps1" -BaseUrl "%BASE_URL%" -Model "%MODEL%" -OllamaUrl "%OLLAMA_URL%" -CostMsatPerMinute %COST% -AvailabilityMinutes %AVAIL% -Visible
