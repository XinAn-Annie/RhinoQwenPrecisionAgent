@echo off
title Rhino Qwen Launcher
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
if errorlevel 1 (
  echo.
  echo Launch failed. See logs\launcher.log.
  pause
)
