@echo off
cd /d "%~dp0"
echo Stopping Deskworlds...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*host\main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Deskworlds stopped.
timeout /t 2 >nul
