@echo off
taskkill /IM nomad_transition_worker.exe /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'nomad_transition_worker.py' -or $_.CommandLine -match 'start_nomad_worker1.ps1' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
schtasks /End /TN "NomadAgent-Autostart" >nul 2>&1
schtasks /End /TN "NomadAgent-Watchdog" >nul 2>&1
echo Nomad Agent stopped.
