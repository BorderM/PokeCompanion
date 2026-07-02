@echo off
setlocal

REM Builds a Windows installer using Inno Setup after build_windows_exe.bat has produced dist\PokemonBattleMonitor.

set "ROOT=%~dp0.."
cd /d "%ROOT%"

if not exist "dist\PokemonBattleMonitor\PokemonBattleMonitor.exe" (
  echo dist\PokemonBattleMonitor\PokemonBattleMonitor.exe was not found.
  echo Run battle_monitor\build_windows_exe.bat first.
  pause
  exit /b 1
)

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  echo Inno Setup 6 was not found.
  echo Install Inno Setup, then run this script again.
  pause
  exit /b 1
)

"%ISCC%" "battle_monitor\build_windows_installer.iss"
if errorlevel 1 (
  echo Installer build failed.
  pause
  exit /b 1
)

echo.
echo Installer complete:
echo   dist\installer\PokemonBattleMonitor_Setup.exe
echo.
pause
