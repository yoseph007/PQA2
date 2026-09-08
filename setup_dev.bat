@echo off
setlocal
cd /d "%~dp0"
echo [BOOTSTRAP] Launching PowerShell developer bootstrap...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_dev.ps1" %*
if errorlevel 1 (
    echo.
    echo [ERROR] setup_dev.ps1 exited with error code %errorlevel%.
    exit /b %errorlevel%
)
exit /b 0
