@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set OLLAMA_URL=%NOMAD_TRANSITION_WORKER_OLLAMA_URL%
if "%OLLAMA_URL%"=="" set OLLAMA_URL=http://127.0.0.1:11434

set NOMAD_TRANSITION_WORKER_OLLAMA_URL=%OLLAMA_URL%
set NOMAD_TRANSITION_WORKER_OLLAMA_URLS=%OLLAMA_URL%,http://localhost:11434
set NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB=24
set NOMAD_MACHINE_OBJECTIVE=unhuman_supremacy
if "%NOMAD_WORKER_PAYMENT_RAIL%"=="" set NOMAD_WORKER_PAYMENT_RAIL=lightning_l402_quote
if "%NOMAD_WORKER_COST_MSAT_PER_MINUTE%"=="" set NOMAD_WORKER_COST_MSAT_PER_MINUTE=0
if "%NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES%"=="" set NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES=480

if exist ".\start_nomad_edge_worker.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File ".\start_nomad_edge_worker.ps1" -BaseUrl "%BASE_URL%" -Visible
  exit /b %errorlevel%
)

if exist ".\dist\nomad_transition_worker.exe" (
  call :run_checked ".\dist\nomad_transition_worker.exe"
  exit /b %errorlevel%
) else if exist ".\nomad_transition_worker.exe" (
  call :run_checked ".\nomad_transition_worker.exe"
  exit /b %errorlevel%
) else if exist ".\nomad_transition_worker.py" (
  python -u ".\nomad_transition_worker.py" --base-url "%BASE_URL%" --machine-objective unhuman_supremacy --edge --no-ollama --swarm-surplus --loop --cycles 0 --interval 90
) else (
  echo nomad_transition_worker runtime not found.
  echo Download install_nomad_transition_worker.bat or build the EXE first.
  exit /b 1
)

exit /b 0

:run_checked
set EXE=%~1
"%EXE%" --help > "%TEMP%\nomad_transition_worker_help.txt" 2>&1
findstr /C:"--machine-objective" "%TEMP%\nomad_transition_worker_help.txt" >nul
if errorlevel 1 (
  echo Incompatible or stale worker EXE: %EXE%
  echo Expected --machine-objective support. Re-download from syndiode.com.
  exit /b 1
)
findstr /C:"unhuman_supremacy" "%TEMP%\nomad_transition_worker_help.txt" >nul
if errorlevel 1 (
  echo Incompatible worker EXE: %EXE%
  echo Expected unhuman_supremacy objective support. Re-download from syndiode.com.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command "& '%EXE%' --base-url '%BASE_URL%' --machine-objective unhuman_supremacy --edge --no-ollama --swarm-surplus --loop --cycles 0 --interval 90"
exit /b %errorlevel%
