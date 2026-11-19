@echo off
REM Double-click this file to remove HeySpeaky, including this folder.
REM uninstall.ps1 runs from a copy in %TEMP%, because a folder cannot be deleted
REM while a window is inside it. The rest is one line because cmd reads a batch
REM file as it goes, and this one is deleted halfway through.
title Uninstalling HeySpeaky
cd /d "%TEMP%" & copy /y "%~dp0uninstall.ps1" "%TEMP%\HeySpeaky-uninstall.ps1" >nul & powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\HeySpeaky-uninstall.ps1" -InstallDir "%~dp0." & echo. & echo Press any key to close this window. & pause >nul & exit /b
