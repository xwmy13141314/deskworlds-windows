@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo  Deskworlds for Windows - Installer
echo ============================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ first.
  pause
  exit /b 1
)

REM 2. Install dependencies
echo [1/4] Installing Python dependencies...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install pywin32 pywebview pystray pillow
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

REM 3. Verify original scenes exist
if not exist "..\deskworlds\scenes\riverscape\wallpaper.html" (
  echo [ERROR] Original deskworlds scenes not found at ..\deskworlds
  echo         Clone https://github.com/chaseleantj/deskworlds next to this folder.
  pause
  exit /b 1
)
echo [2/4] Scenes found: OK

REM 4. Register autostart (current user)
echo [3/4] Registering Start-with-Windows (current user)...
python host\autostart.py enable

echo [4/4] Done. Use run.bat to start, or it will launch at next login.
echo.
echo Tip: Look for the Deskworlds icon in the system tray.
echo.
pause
