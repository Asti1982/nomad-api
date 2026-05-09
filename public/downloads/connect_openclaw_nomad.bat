@echo off
setlocal EnableExtensions
REM OPTIONAL / secondary path: OpenClaw runtime probe + nomad_openclaw_adapter.py
REM Recommended default for swarm compute: install_nomad_transition_worker.bat (no OpenClaw).
REM Optional: first arg = base URL (default syndiode). Second arg = extra flags for python (quoted), e.g. "--idle-earn"

set "BASE_URL=%~1"
if "%BASE_URL%"=="" set "BASE_URL=https://www.syndiode.com"
set "EXTRA=%~2"

set "DIR=%USERPROFILE%\NomadOpenClawBridge"
set "ADAPTER=%DIR%\nomad_openclaw_adapter.py"

if not exist "%DIR%" mkdir "%DIR%" 2>nul

if not exist "%ADAPTER%" (
  echo [Nomad] Lade Adapter nach "%ADAPTER%" ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%BASE_URL%/downloads/nomad_openclaw_adapter.py' -OutFile '%ADAPTER%'"
  if errorlevel 1 (
    echo Download fehlgeschlagen. Pruefe Netz und BASE_URL.
    exit /b 1
  )
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python 3 fehlt im PATH. Bitte installieren und dieses Skript erneut starten.
  exit /b 1
)

where openclaw >nul 2>&1
if errorlevel 1 (
  echo Hinweis: "openclaw" nicht im PATH — Adapter startet trotzdem; Laufzeit-Sonde dann ohne OpenClaw.
) else (
  echo [OpenClaw] Kurzcheck ...
  openclaw health --json --timeout 8000 2>nul
)

echo.
echo [Nomad] Bridge laeuft gegen %BASE_URL%
echo     Stop: Strg+C
echo.

if defined EXTRA (
  python "%ADAPTER%" --base-url "%BASE_URL%" --loop --cycles 0 --interval 12 %EXTRA%
) else (
  python "%ADAPTER%" --base-url "%BASE_URL%" --loop --cycles 0 --interval 12
)
exit /b %ERRORLEVEL%
