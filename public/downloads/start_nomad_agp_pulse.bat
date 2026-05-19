@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_nomad_agp_pulse.ps1" %*
