@echo off
title Ang2React - Angular to React Migration Tool
echo.
echo  ============================================
echo   Ang2React - Angular to React Migration
echo  ============================================
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo [1/3] Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python not found. Install Python 3.11+ and try again.
        pause
        exit /b 1
    )
)

echo [2/3] Installing dependencies and patching ADK...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check
python patch_adk.py

echo [3/3] Starting server...
echo.
echo  Open your browser at: http://localhost:8000
echo  Press Ctrl+C to stop the server.
echo.

uvicorn server.app:app --host 0.0.0.0 --port 8000

pause
