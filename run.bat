@echo off
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ first.
  pause
  exit /b 1
)

echo Starting Deskworlds wallpaper...
echo The console window will minimize itself in 2 seconds.
echo Press Win+D to see the desktop wallpaper.
echo Use the system tray icon to control or exit.
echo.

python host\main.py
