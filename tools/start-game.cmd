@echo off
rem ---------------------------------------------------------------------------
rem Start Stardew Valley WITH SMAPI (ASCII-only on purpose).
rem
rem Why SMAPI: launching "Stardew Valley.exe" starts the VANILLA game and our
rem bridge mod will not load. Only StardewModdingAPI.exe loads mods.
rem
rem Why Steam is NOT started by default:
rem   * Stardew has no Steam DRM - it runs standalone (steam_appid.txt exists for
rem     exactly this). Verified 2026-10-11: Steam's API can fail to load
rem     ("[API loaded no]") and the game still runs fine.
rem   * Steam Cloud sync for this game IS ENABLED on this machine. Verified that
rem     it pushed the save right after a test session (remotecache.vdf timestamp
rem     2026-10-11 17:19:55). Cloud sync can silently overwrite or "repair" our
rem     test save, which would make save-backups\ meaningless.
rem   => keep Steam out of the loop. Pass --with-steam only if you really want it.
rem
rem Usage:
rem   tools\start-game.cmd                 (recommended: no Steam)
rem   tools\start-game.cmd --with-steam    (start Steam first, e.g. for achievements)
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

rem --- optional: start Steam only when explicitly asked ----------------
if /i "%~1"=="--with-steam" (
  if exist "%STEAM%" (
    echo Starting Steam ^(--with-steam^) and waiting 20s...
    start "" "%STEAM%"
    timeout /t 20 /nobreak >nul
  ) else (
    echo [WARN] Steam not found at "%STEAM%"
  )
)

rem --- warn if Steam happens to be running: cloud sync may fire on exit ---
tasklist /fi "imagename eq steam.exe" 2>nul | find /i "steam.exe" >nul
if not errorlevel 1 (
  echo [WARN] Steam IS running. Steam Cloud sync for Stardew is ENABLED on this
  echo        machine, so it may sync the save when the game exits.
  echo        Safest: turn off Steam Cloud for Stardew (Library -^> right-click
  echo        Stardew Valley -^> Properties -^> General -^> uncheck cloud saves^),
  echo        or close Steam before automated runs.
)

echo Starting: "%GAME%\StardewModdingAPI.exe"
start "" "%GAME%\StardewModdingAPI.exe"

echo.
echo Next steps in game:
echo   1) Load your save (Single Player -^> Load -^> your farm).
echo   2) Watch the SMAPI console for: AgentFarm Bridge v0.2.0
echo   3) Then run:  tools\agentfarm.cmd doctor
exit /b 0
