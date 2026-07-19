@echo off
REM Start API without activating venv (avoids PowerShell script policy)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup first:  py -m venv .venv
    echo Then:  .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)
.venv\Scripts\python.exe app.py
pause
