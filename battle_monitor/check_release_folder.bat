@echo off
setlocal

REM Quick local sanity check for the portable release folder.

set "ROOT=%~dp0.."
set "DIST_APP=%ROOT%\dist\PokemonBattleMonitor"

python "%ROOT%\battle_monitor\check_release_folder.py" --dist "%DIST_APP%"
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
echo Optional Windows Defender scan:
echo   powershell -Command "Start-MpScan -ScanType CustomScan -ScanPath '%DIST_APP%'"
echo.
pause
