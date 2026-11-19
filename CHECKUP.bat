@echo off
REM Double-click this file to check whether HeySpeaky is set up correctly.
cd /d "%~dp0"
title HeySpeaky check-up
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0tools\doctor.py"
) else (
  echo HeySpeaky is not installed yet -- run INSTALL.bat first.
)
echo.
echo Press any key to close this window.
pause >nul
