@echo off
setlocal enabledelayedexpansion

REM Debug Nuitka build. Use this if the normal GUI exe appears to do nothing.
REM It keeps the console visible so startup errors are printed directly.

set "ROOT=%~dp0.."
cd /d "%ROOT%"

set "VENDOR_TESS=%ROOT%\battle_monitor\vendor\tesseract"
set "NUITKA_BUILD=%ROOT%\dist_nuitka_debug_build"
set "DIST_APP=%ROOT%\dist\PokemonBattleMonitor_Debug"
set "ENTRY=%ROOT%\battle_monitor\battle_monitor_launcher.py"

if not exist "%ENTRY%" (
  echo Could not find launcher entry file:
  echo   %ENTRY%
  pause
  exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r battle_monitor\requirements-battle-monitor.txt nuitka ordered-set zstandard

if exist "%NUITKA_BUILD%" rmdir /s /q "%NUITKA_BUILD%"
if exist "%DIST_APP%" rmdir /s /q "%DIST_APP%"
mkdir "%DIST_APP%"

echo.
echo Building DEBUG console version with Nuitka...
echo Entry: %ENTRY%
echo.

if exist "%VENDOR_TESS%\tesseract.exe" (
  python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=force ^
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
  python -m nuitka --standalone --assume-yes-for-downloads --enable-plugin=tk-inter --windows-console-mode=force ^
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
  echo Debug Nuitka build failed.
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

if exist "%VENDOR_TESS%\tesseract.exe" if not exist "%DIST_APP%\tesseract\tesseract.exe" (
  xcopy "%VENDOR_TESS%\*" "%DIST_APP%\tesseract\" /E /I /Y >nul
)

(
  echo @echo off
  echo cd /d "%%~dp0"
  echo echo Running Pokemon Battle Monitor debug build...
  echo echo.
  echo PokemonBattleMonitor.exe
  echo echo.
  echo echo Exit code: %%ERRORLEVEL%%
  echo echo.
  echo echo Startup logs, if present:
  echo echo   %%~dp0battle_monitor\startup.log
  echo echo   %%~dp0battle_monitor\startup_error.log
  echo echo.
  echo pause
) > "%DIST_APP%\RUN_DEBUG.bat"

echo.
echo Debug build complete.
echo Folder: dist\PokemonBattleMonitor_Debug
echo Run:
echo   dist\PokemonBattleMonitor_Debug\RUN_DEBUG.bat
echo.
pause
