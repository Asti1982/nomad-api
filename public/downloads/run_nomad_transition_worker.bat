@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
python nomad_transition_worker.py --base-url %BASE_URL% --loop --cycles 0
