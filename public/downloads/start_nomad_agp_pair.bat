@echo off
setlocal
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://www.syndiode.com
set SCRIPT_DIR=%~dp0
set COST=%NOMAD_WORKER_COST_MSAT_PER_MINUTE%
if "%COST%"=="" set COST=0
set AVAIL=%NOMAD_WORKER_MARKET_AVAILABILITY_MINUTES%
if "%AVAIL%"=="" set AVAIL=480
set INTERVAL=%NOMAD_AGP_PAIR_INTERVAL_SECONDS%
if "%INTERVAL%"=="" set INTERVAL=90
set TIMEOUT=%NOMAD_AGP_PAIR_TIMEOUT_SECONDS%
if "%TIMEOUT%"=="" set TIMEOUT=30
set PROPOSER_ID=%NOMAD_AGP_PROPOSER_ID%
if "%PROPOSER_ID%"=="" set PROPOSER_ID=nomad-agp-proposer-local
set VERIFIER_ID=%NOMAD_AGP_VERIFIER_ID%
if "%VERIFIER_ID%"=="" set VERIFIER_ID=nomad-agp-verifier-local
set MODEL=%NOMAD_AGP_PAIR_MODEL%
if "%MODEL%"=="" set MODEL=auto
set OLLAMA_URL=%NOMAD_TRANSITION_WORKER_OLLAMA_URL%
if "%OLLAMA_URL%"=="" set OLLAMA_URL=http://127.0.0.1:11434
set NO_OLLAMA_FLAG=
if "%NOMAD_AGP_NO_OLLAMA%"=="1" set NO_OLLAMA_FLAG=-NoOllama
set CODEX_FLAG=
if "%NOMAD_AGP_CODEX_PROPOSER%"=="1" set CODEX_FLAG=-CodexProposer

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_nomad_agp_pair.ps1" -BaseUrl "%BASE_URL%" -ProposerAgentId "%PROPOSER_ID%" -VerifierAgentId "%VERIFIER_ID%" -Model "%MODEL%" -OllamaUrl "%OLLAMA_URL%" -CostMsatPerMinute %COST% -AvailabilityMinutes %AVAIL% -IntervalSeconds %INTERVAL% -TimeoutSeconds %TIMEOUT% %NO_OLLAMA_FLAG% %CODEX_FLAG% -Visible
