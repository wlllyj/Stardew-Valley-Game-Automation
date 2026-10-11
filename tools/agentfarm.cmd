@echo off
rem ---------------------------------------------------------------------------
rem AgentFarm brain launcher (ASCII-only on purpose).
rem
rem Why this file exists:
rem   1) PowerShell execution policy blocks .ps1 on this machine
rem      ("running scripts is disabled"), so we relaunch with -ExecutionPolicy Bypass.
rem   2) Python defaults to the system locale encoding (cp1252 here) when stdout is
rem      redirected, which crashes on Chinese output; PYTHONUTF8/PYTHONIOENCODING fix it.
rem
rem We prefer pwsh (PowerShell 7) and fall back to powershell (5.1).
rem The target .ps1 is ASCII-only so either host parses it correctly.
rem
rem Usage:
rem   tools\agentfarm.cmd doctor
rem   tools\agentfarm.cmd observe
rem   tools\agentfarm.cmd move 64 15
rem ---------------------------------------------------------------------------
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0agentfarm.ps1" %*
exit /b %ERRORLEVEL%
