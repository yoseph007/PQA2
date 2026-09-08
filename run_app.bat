@echo off
setlocal
cd /d "%~dp0"
echo Starting VMAF Test Application (PyQt6)...
call .venv\Scripts\python.exe main.py
if errorlevel 1 (
    echo.
    echo Application exited with error code %errorlevel%.
    pause
)
