@echo off
setlocal enabledelayedexpansion

REM Safe PyInstaller build for Pokemon Battle Monitor.
REM Uses one-folder mode and --noupx to reduce antivirus false positives.
REM If Windows Defender still removes the generated EXE, try build_windows_exe_nuitka.bat.

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VENDOR_TESS=%ROOT%\battle_monitor\vendor\tesseract"
set "DIST_APP=%ROOT%\dist\PokemonBattleMonitor"
set "BUILD_DIR=%ROOT%\build"

if not exist "%VENDOR_TESS%\tesseract.exe" (
  echo Portable Tesseract is not prepared yet.
  echo.
  echo To make the build self-contained, run:
  echo   battle_monitor\prepare_portable_tesseract.bat
  echo.
  echo This copies your local Tesseract install into:
  echo   battle_monitor\vendor\tesseract
  echo.
  set /p CONTINUE="Continue without bundled Tesseract? The app will not be self-contained. [y/N] "
  if /I not "!CONTINUE!"=="Y" exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r battle_monitor\requirements-battle-monitor.txt pyinstaller

if exist "%DIST_APP%" rmdir /s /q "%DIST_APP%"
if exist "%BUILD_DIR%\PokemonBattleMonitor" rmdir /s /q "%BUILD_DIR%\PokemonBattleMonitor"
if exist "PokemonBattleMonitor.spec" del /q "PokemonBattleMonitor.spec"

pyinstaller --noconfirm --clean --windowed --onedir --noupx ^
  --name PokemonBattleMonitor ^
  --add-data "processed_pokemon_cache.json;." ^
  --add-data "pokemon_cache.json;." ^
  --add-data "data;data" ^
  --add-data "static\processed_pokemon_cache.json;static" ^
  --add-data "static\form_reference.json;static" ^
  --add-data "static\pokemon_reference_map_types.json;static" ^
  --add-data "static\pokemon_reference_map_stats.json;static" ^
  --add-data "static\typechart.json;static" ^
  --add-data "battle_monitor\DISTRIBUTION_CHECKLIST.md;battle_monitor" ^
  --add-data "battle_monitor\RELEASE_BUILD.md;battle_monitor" ^
  battle_monitor\battle_monitor_launcher.py

if errorlevel 1 (
  echo.
  echo PyInstaller build failed.
  echo.
  echo If the message said "contains a virus or potentially unwanted software",
  echo Windows Defender most likely quarantined the generated PyInstaller bootloader.
  echo This is a known false-positive pattern with some unsigned PyInstaller apps.
  echo.
  echo Recommended next step:
  echo   battle_monitor\build_windows_exe_nuitka.bat
  echo.
  pause
  exit /b 1
)

if not exist "%DIST_APP%\PokemonBattleMonitor.exe" (
  echo.
  echo Build folder was created, but PokemonBattleMonitor.exe is missing.
  echo It may have been quarantined by antivirus.
  echo.
  echo Recommended next step:
  echo   battle_monitor\build_windows_exe_nuitka.bat
  echo.
  pause
  exit /b 1
)

if exist "%VENDOR_TESS%\tesseract.exe" (
  echo Copying bundled Tesseract into dist folder...
  if exist "%DIST_APP%\tesseract" rmdir /s /q "%DIST_APP%\tesseract"
  xcopy "%VENDOR_TESS%\*" "%DIST_APP%\tesseract\" /E /I /Y >nul
  if errorlevel 1 (
    echo Failed to copy portable Tesseract.
    pause
    exit /b 1
  )
)

if not exist "%DIST_APP%\tesseract\tesseract.exe" (
  echo.
  echo WARNING: No bundled Tesseract was copied.
  echo The app will require Tesseract to be installed on the user's machine.
) else (
  echo.
  echo Bundled Tesseract found:
  echo   %DIST_APP%\tesseract\tesseract.exe
)


(
  echo @echo off
  echo cd /d "%%~dp0"
  echo echo Starting Pokemon Battle Monitor...
  echo echo If nothing opens, this helper will show startup logs after the process exits.
  echo echo.
  echo start "" /wait PokemonBattleMonitor.exe
  echo echo.
  echo echo Exit code: %%ERRORLEVEL%%
  echo echo.
  echo if exist "battle_monitor\startup.log" ^(
  echo   echo ===== startup.log =====
  echo   type "battle_monitor\startup.log"
  echo   echo.
  echo ^)
  echo if exist "battle_monitor\startup_error.log" ^(
  echo   echo ===== startup_error.log =====
  echo   type "battle_monitor\startup_error.log"
  echo   echo.
  echo ^)
  echo pause
) > "%DIST_APP%\RUN_AND_SHOW_LOGS.bat"

python battle_monitor\check_release_folder.py --dist "%DIST_APP%"
if errorlevel 1 (
  echo.
  echo Release validation failed.
  pause
  exit /b 1
)

echo.
echo Build complete.
echo EXE: dist\PokemonBattleMonitor\PokemonBattleMonitor.exe
echo.
echo To share as a portable app, zip the entire folder:
echo   dist\PokemonBattleMonitor
echo.
pause
