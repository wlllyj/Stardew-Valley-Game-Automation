@echo off
rem ---------------------------------------------------------------------------
rem Start Stardew Valley WITH SMAPI (ASCII-only on purpose).
rem
rem Why: launching "Stardew Valley.exe" (or Steam's Play button, unless a launch
rem option was configured) starts the VANILLA game and our bridge mod will not load.
rem Only StardewModdingAPI.exe loads mods.
rem
rem Usage:
rem   tools\start-game.cmd
rem   set STARDEW_GAME_PATH=E:\...\Stardew Valley   (override game folder)
rem ---------------------------------------------------------------------------
setlocal
set "GAME=D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
if defined STARDEW_GAME_PATH set "GAME=%STARDEW_GAME_PATH%"
set "STEAM=D:\Program Files (x86)\Steam\steam.exe"

if not exist "%GAME%\StardewModdingAPI.exe" (
  echo [ERROR] SMAPI not found: "%GAME%\StardewModdingAPI.exe"
  echo         Set STARDEW_GAME_PATH to your Stardew Valley folder.
  exit /b 1
)

rem Stardew needs Steam running for the Steam API; start it if needed.
tasklist /fi "imagename eq steam.exe" 2>nul | find /i "steam.exe" >nul
if errorlevel 1 (
  if exist "%STEAM%" (
    echo Steam is not running - starting it and waiting 20s...
    start "" "%STEAM%"
    timeout /t 20 /nobreak >nul
  ) else (
    echo [WARN] Steam not found at "%STEAM%" - launching the game anyway.
  )
)

echo Starting: "%GAME%\StardewModdingAPI.exe"
start "" "%GAME%\StardewModdingAPI.exe"

echo.
echo Next steps in game:
echo   1) Load your save (Single Player -^> Load -^> your farm).
echo   2) Watch the SMAPI console for: AgentFarm Bridge v0.1.0 ready
echo   3) Then run:  tools\agentfarm.cmd doctor
exit /b 0
