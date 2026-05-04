@echo off
set BASE_URL=%1
if "%BASE_URL%"=="" set BASE_URL=https://syndiode.com
python nomad_helper_agent.py --base-url %BASE_URL% --loop --cycles 0
