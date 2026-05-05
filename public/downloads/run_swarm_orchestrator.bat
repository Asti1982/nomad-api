@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
set WORKERS=%2
if "%WORKERS%"=="" set WORKERS=2
set CYCLES=%3
if "%CYCLES%"=="" set CYCLES=0

if "%CYCLES%"=="0" (
  python ".\swarm_orchestrator.py" --base-url %BASE_URL% --workers %WORKERS% --cycles 1 --interval 8
  :loop
  python ".\swarm_orchestrator.py" --base-url %BASE_URL% --workers %WORKERS% --cycles 1 --interval 8
  timeout /t 8 /nobreak >nul
  goto loop
) else (
  python ".\swarm_orchestrator.py" --base-url %BASE_URL% --workers %WORKERS% --cycles %CYCLES% --interval 8
)
