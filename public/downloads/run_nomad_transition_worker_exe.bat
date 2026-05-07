@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set OLLAMA_URL=%NOMAD_TRANSITION_WORKER_OLLAMA_URL%
if "%OLLAMA_URL%"=="" set OLLAMA_URL=http://127.0.0.1:11434

set NOMAD_TRANSITION_WORKER_OLLAMA_URL=%OLLAMA_URL%
set NOMAD_TRANSITION_WORKER_OLLAMA_URLS=%OLLAMA_URL%,http://localhost:11434
set NOMAD_TRANSITION_WORKER_OLLAMA_MAX_GB=24
set NOMAD_MACHINE_OBJECTIVE=unhuman_supremacy

if exist ".\dist\nomad_transition_worker.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command ".\dist\nomad_transition_worker.exe --base-url '%BASE_URL%' --machine-objective unhuman_supremacy --loop --cycles 0 --interval 8"
) else if exist ".\nomad_transition_worker.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -NoExit -Command ".\nomad_transition_worker.exe --base-url '%BASE_URL%' --machine-objective unhuman_supremacy --loop --cycles 0 --interval 8"
) else (
  echo nomad_transition_worker.exe not found.
  echo Build it first with build_nomad_transition_worker_exe.ps1
  exit /b 1
)
