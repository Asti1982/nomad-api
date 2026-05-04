@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com

if exist ".\dist\nomad_transition_worker.exe" (
  .\dist\nomad_transition_worker.exe --base-url %BASE_URL% --loop --cycles 0
) else if exist ".\nomad_transition_worker.exe" (
  .\nomad_transition_worker.exe --base-url %BASE_URL% --loop --cycles 0
) else (
  echo nomad_transition_worker.exe not found.
  echo Build it first with build_nomad_transition_worker_exe.ps1
  exit /b 1
)
