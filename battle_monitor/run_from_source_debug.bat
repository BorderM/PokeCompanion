@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"
python -m pip install -r battle_monitor\requirements-battle-monitor.txt
python battle_monitor\battle_monitor_launcher.py
pause
