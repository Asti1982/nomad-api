@echo off
taskkill /IM nomad_transition_worker.exe /F >nul 2>&1
schtasks /End /TN "NomadAgent-Autostart" >nul 2>&1
schtasks /End /TN "NomadAgent-Watchdog" >nul 2>&1
echo Nomad Agent stopped.
