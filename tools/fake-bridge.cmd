@echo off
rem ---------------------------------------------------------------------------
rem Start the FAKE mod (mock world) so the brain can be exercised without the game.
rem ASCII-only on purpose; see tools\agentfarm.cmd for the reasons.
rem
rem Usage:
rem   tools\fake-bridge.cmd                 (listens on 17899)
rem   tools\fake-bridge.cmd --port 17950
rem
rem Then, in ANOTHER terminal:
rem   set AGENTFARM_BRIDGE_JSON=%CD%\brain\run\fake-bridge.json
rem   tools\agentfarm.cmd doctor
rem ---------------------------------------------------------------------------
setlocal
set "PY="
if defined AGENTFARM_PYTHON if exist "%AGENTFARM_PYTHON%" set "PY=%AGENTFARM_PYTHON%"
if not defined PY if exist "%~dp0..\brain\.venv\Scripts\python.exe" set "PY=%~dp0..\brain\.venv\Scripts\python.exe"
if not defined PY if exist "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PY=C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PY if exist "C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul') do if not defined PY echo %%i | find /i "WindowsApps" >nul || set "PY=%%i"
if not defined PY (
  echo No usable Python found. Set AGENTFARM_PYTHON to a python.exe path.
  exit /b 1
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%PY%" "%~dp0fake_bridge.py" --out "%~dp0..\brain\run\fake-bridge.json" %*
exit /b %ERRORLEVEL%
