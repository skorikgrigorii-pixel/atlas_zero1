@echo off
cd /d %~dp0
set PYTHONPATH=%CD%\src
python -m az_enterprise.timeline_viewer_app
pause
