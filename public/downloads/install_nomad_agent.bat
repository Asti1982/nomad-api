@echo off
setlocal
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
set TARGET=%TEMP%\install_nomad_transition_worker.bat

echo Downloading installer from %BASE_URL%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%BASE_URL%/downloads/install_nomad_transition_worker.bat' -OutFile '%TARGET%'"
if errorlevel 1 (
  echo Failed to download installer.
  exit /b 1
)

echo Running installer...
call "%TARGET%" "%BASE_URL%"
