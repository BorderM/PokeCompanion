@echo off
setlocal enabledelayedexpansion

REM Alternative release build using Nuitka instead of PyInstaller.
REM Recommended if Windows Defender quarantines the PyInstaller build.
REM v14 fix: keep every include path quoted so Nuitka only receives ONE positional argument:
REM          battle_monitor\battle_monitor_launcher.py

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VENDOR_TESS=%ROOT%\battle_monitor\vendor\tesseract"
set "NUITKA_BUILD=%ROOT%\dist_nuitka_build"
set "DIST_APP=%ROOT%\dist\PokemonBattleMonitor"
set "ENTRY=%ROOT%\battle_monitor\battle_monitor_launcher.py"

if not exist "%ENTRY%" (
  echo Could not find launcher entry file:
  echo   %ENTRY%
  pause
  exit /b 1
)

if not exist "%VENDOR_TESS%\tesseract.exe" (
  echo Portable Tesseract is not prepared yet.
  echo.
  echo To make the build self-contained, run:
  echo   battle_monitor\prepare_portable_tesseract.bat
  echo.
  set /p CONTINUE="Continue without bundled Tesseract? The app will not be self-contained. [y/N] "
  if /I not "!CONTINUE!"=="Y" exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r battle_monitor\requirements-battle-monitor.txt nuitka ordered-set zstandard

if exist "%NUITKA_BUILD%" rmdir /s /q "%NUITKA_BUILD%"
if exist "%DIST_APP%" rmdir /s /q "%DIST_APP%"
mkdir "%DIST_APP%"

echo.
echo Building with Nuitka...
echo Entry: %ENTRY%
echo Output build folder: %NUITKA_BUILD%
echo.

if exist "%VENDOR_TESS%\tesseract.exe" (
  python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=disable ^
    --output-dir="%NUITKA_BUILD%" ^
    --output-filename=PokemonBattleMonitor.exe ^
    --include-data-files="%ROOT%\processed_pokemon_cache.json=processed_pokemon_cache.json" ^
    --include-data-files="%ROOT%\pokemon_cache.json=pokemon_cache.json" ^
    --include-data-dir="%ROOT%\data=data" ^
    --include-data-files="%ROOT%\static\processed_pokemon_cache.json=static\processed_pokemon_cache.json" ^
    --include-data-files="%ROOT%\static\form_reference.json=static\form_reference.json" ^
    --include-data-files="%ROOT%\static\pokemon_reference_map_types.json=static\pokemon_reference_map_types.json" ^
    --include-data-files="%ROOT%\static\pokemon_reference_map_stats.json=static\pokemon_reference_map_stats.json" ^
    --include-data-files="%ROOT%\static\typechart.json=static\typechart.json" ^
    --include-data-files="%ROOT%\battle_monitor\DISTRIBUTION_CHECKLIST.md=battle_monitor\DISTRIBUTION_CHECKLIST.md" ^
    --include-data-files="%ROOT%\battle_monitor\RELEASE_BUILD.md=battle_monitor\RELEASE_BUILD.md" ^
    --include-data-dir="%VENDOR_TESS%=tesseract" ^
    "%ENTRY%"
) else (
  python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=disable ^
    --output-dir="%NUITKA_BUILD%" ^
    --output-filename=PokemonBattleMonitor.exe ^
    --include-data-files="%ROOT%\processed_pokemon_cache.json=processed_pokemon_cache.json" ^
    --include-data-files="%ROOT%\pokemon_cache.json=pokemon_cache.json" ^
    --include-data-dir="%ROOT%\data=data" ^
    --include-data-files="%ROOT%\static\processed_pokemon_cache.json=static\processed_pokemon_cache.json" ^
    --include-data-files="%ROOT%\static\form_reference.json=static\form_reference.json" ^
    --include-data-files="%ROOT%\static\pokemon_reference_map_types.json=static\pokemon_reference_map_types.json" ^
    --include-data-files="%ROOT%\static\pokemon_reference_map_stats.json=static\pokemon_reference_map_stats.json" ^
    --include-data-files="%ROOT%\static\typechart.json=static\typechart.json" ^
    --include-data-files="%ROOT%\battle_monitor\DISTRIBUTION_CHECKLIST.md=battle_monitor\DISTRIBUTION_CHECKLIST.md" ^
    --include-data-files="%ROOT%\battle_monitor\RELEASE_BUILD.md=battle_monitor\RELEASE_BUILD.md" ^
    "%ENTRY%"
)

if errorlevel 1 (
  echo.
  echo Nuitka build failed.
  echo.
  echo If you see "specify only one positional argument", make sure you are using v14 or newer.
  echo The v14 script quotes all data paths and passes only this entry file as the positional argument:
  echo   %ENTRY%
  echo.
  echo If this is the first Nuitka build on the machine, also check that the C compiler download/install completed.
  pause
  exit /b 1
)

set "NUITKA_OUT="
for /d %%D in ("%NUITKA_BUILD%\*.dist") do set "NUITKA_OUT=%%~fD"

if not defined NUITKA_OUT (
  echo Could not find Nuitka .dist output under:
  echo   %NUITKA_BUILD%
  pause
  exit /b 1
)

xcopy "!NUITKA_OUT!\*" "%DIST_APP%\" /E /I /Y >nul
if errorlevel 1 (
  echo Failed to copy Nuitka output to:
  echo   %DIST_APP%
  pause
  exit /b 1
)

if not exist "%DIST_APP%\PokemonBattleMonitor.exe" (
  echo.
  echo Nuitka output copied, but PokemonBattleMonitor.exe is missing.
  echo It may have been blocked or quarantined by antivirus.
  pause
  exit /b 1
)

if exist "%VENDOR_TESS%\tesseract.exe" if not exist "%DIST_APP%\tesseract\tesseract.exe" (
  echo Copying bundled Tesseract into dist folder...
  xcopy "%VENDOR_TESS%\*" "%DIST_APP%\tesseract\" /E /I /Y >nul
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
echo Nuitka build complete.
echo EXE: dist\PokemonBattleMonitor\PokemonBattleMonitor.exe
echo.
echo To share as a portable app, zip the entire folder:
echo   dist\PokemonBattleMonitor
echo.
pause
