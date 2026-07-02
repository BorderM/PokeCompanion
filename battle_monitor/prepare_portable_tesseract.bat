@echo off
setlocal enabledelayedexpansion

REM Copies an existing Windows Tesseract install into the app's portable vendor folder.
REM Usage:
REM   battle_monitor\prepare_portable_tesseract.bat
REM   battle_monitor\prepare_portable_tesseract.bat "C:\Program Files\Tesseract-OCR"

set "ROOT=%~dp0.."
set "VENDOR=%ROOT%\battle_monitor\vendor\tesseract"
set "SRC=%~1"

if not defined SRC (
  if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set "SRC=C:\Program Files\Tesseract-OCR"
)
if not defined SRC (
  if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" set "SRC=C:\Program Files (x86)\Tesseract-OCR"
)

if not defined SRC (
  echo Could not find Tesseract automatically.
  echo.
  echo Install Tesseract for Windows, then run this again with the install folder:
  echo   battle_monitor\prepare_portable_tesseract.bat "C:\Program Files\Tesseract-OCR"
  echo.
  pause
  exit /b 1
)

if not exist "%SRC%\tesseract.exe" (
  echo tesseract.exe was not found in:
  echo   %SRC%
  echo.
  pause
  exit /b 1
)

if not exist "%SRC%\tessdata\eng.traineddata" (
  echo English OCR data was not found at:
  echo   %SRC%\tessdata\eng.traineddata
  echo.
  echo Reinstall Tesseract with English language data, then try again.
  pause
  exit /b 1
)

if exist "%VENDOR%" rmdir /s /q "%VENDOR%"
mkdir "%VENDOR%"

xcopy "%SRC%\*" "%VENDOR%\" /E /I /Y >nul
if errorlevel 1 (
  echo Failed to copy Tesseract into:
  echo   %VENDOR%
  pause
  exit /b 1
)

echo.
echo Portable Tesseract prepared at:
echo   %VENDOR%
echo.
echo The build script will copy this folder into the final app beside PokemonBattleMonitor.exe.
echo.
pause
