@echo off
REM Double-click this file to install HeySpeaky.
REM It is a thin wrapper around install.ps1 so that nobody has to open
REM PowerShell or know what an execution policy is.
cd /d "%~dp0"
title Installing HeySpeaky
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
echo Press any key to close this window.
pause >nul
