@echo off
REM App Manager — start FastAPI (Command Prompt / double-click)
REM Usage: cd backend
REM        run.bat

cd /d "%~dp0"

set PYTHON=%~dp0.venv\Scripts\python.exe
set PIP=%~dp0.venv\Scripts\pip.exe

if not exist "%PYTHON%" (
    echo Virtual environment not found. Creating .venv ...
    where py >nul 2>&1
    if %ERRORLEVEL%==0 (
        py -m venv "%~dp0.venv"
    ) else (
        where python >nul 2>&1
        if %ERRORLEVEL%==0 (
            python -m venv "%~dp0.venv"
        ) else (
            echo ERROR: Python is not installed. Install from https://www.python.org/downloads/
            pause
            exit /b 1
        )
    )
)

if not exist "%~dp0.venv\Scripts\uvicorn.exe" (
    echo Installing dependencies ...
    "%PIP%" install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo ERROR: pip install failed
        pause
        exit /b 1
    )
)

echo.
echo   App Manager API
echo   http://127.0.0.1:8000
echo   Docs: http://127.0.0.1:8000/docs
echo   Press Ctrl+C to stop
echo.

"%PYTHON%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
pause
