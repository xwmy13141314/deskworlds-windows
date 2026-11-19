@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Deskworlds for Windows - Uninstall
echo ============================================
echo.

echo Removing Start-with-Windows entry...
python host\autostart.py disable

echo.
echo Deskworlds launch entry removed.
echo (Your config at %%APPDATA%%\Deskworlds and the original scenes are left intact.)
echo.
pause
