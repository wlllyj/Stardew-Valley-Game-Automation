@echo off
rem ---------------------------------------------------------------------------
rem Snapshot the Stardew save folder before any automated run (ASCII-only).
rem
rem Why: decision D8 chose to test against the REAL save. Save corruption is
rem irreversible, so every automated run must be preceded by a snapshot.
rem The brain will call this automatically at startup; run it by hand to be safe.
rem
rem Usage:
rem   tools\backup-save.cmd
rem   set STARDEW_SAVES_DIR=E:\...\Saves   (override)
rem ---------------------------------------------------------------------------
setlocal
set "SAVES=%APPDATA%\StardewValley\Saves"
if defined STARDEW_SAVES_DIR set "SAVES=%STARDEW_SAVES_DIR%"
set "DEST=%~dp0..\save-backups"

if not exist "%SAVES%" (
  echo [ERROR] Save folder not found: "%SAVES%"
  exit /b 1
)

for /f "tokens=1-4 delims=/:. " %%a in ("%DATE% %TIME%") do set "STAMP=%%a%%b%%c-%%d"
set "TARGET=%DEST%\%STAMP%"

mkdir "%DEST%" 2>nul
echo Snapshot: "%SAVES%"  ->  "%TARGET%"
xcopy "%SAVES%" "%TARGET%\" /E /I /H /Y /Q >nul
if errorlevel 1 (
  echo [ERROR] Snapshot failed.
  exit /b 1
)

echo Done. Contents:
dir /b "%TARGET%"
exit /b 0
