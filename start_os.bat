@echo off
cd /d %~dp0
set PYTHONPATH=%CD%\src
python -m az_enterprise.ui.app
pause
