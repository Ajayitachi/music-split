@echo off
rem Double-click to install Multi Headphones (Start Menu + Desktop shortcut). No admin needed.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 pause
