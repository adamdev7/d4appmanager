@echo off
REM Start backend + frontend (dev mode)
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo Backend venv missing. Run:
    echo   cd backend
    echo   py -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

call :find_node
if not defined NPM_CMD (
    echo.
    echo  [WARNING] Node.js was not found.
    echo  Install from https://nodejs.org/ then run this script again.
    echo.
    start "App Manager API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe app.py"
    pause
    exit /b 1
)

REM Broken partial install puts a fake npm inside node_modules — use system npm only
if exist "frontend\node_modules\npm" (
    echo Broken node_modules detected. Run fix-frontend.bat first.
    pause
    exit /b 1
)

if not exist "frontend\node_modules\vite" (
    echo Installing frontend dependencies...
    cd frontend
    call "%NPM_CMD%" install
    if errorlevel 1 (
        echo.
        echo npm install failed. Run:  .\fix-frontend.bat
        cd ..
        pause
        exit /b 1
    )
    cd ..
)

echo.
echo  Starting App Manager...
echo  ----------------------------------------
echo   Dashboard (UI):  http://localhost:5173  ^<-- open this in your browser
echo   API / docs:      http://127.0.0.1:8000
echo  ----------------------------------------
echo.

start "App Manager API" cmd /k "set PATH=%NODE_DIR%;%PATH%&& cd /d "%~dp0backend" && .venv\Scripts\python.exe app.py"
timeout /t 2 /nobreak >nul
start "App Manager UI" cmd /k "set PATH=%NODE_DIR%;%PATH%&& cd /d "%~dp0frontend" && npm run dev"

echo Two windows opened. Use http://localhost:5173 for the app.
pause
exit /b 0

:find_node
set "NPM_CMD="
set "NODE_DIR="
REM Always prefer real Node.js install — never "where npm" (can hit broken local copy)
if exist "%ProgramFiles%\nodejs\npm.cmd" set "NODE_DIR=%ProgramFiles%\nodejs"
if not defined NODE_DIR if exist "%LocalAppData%\Programs\node\npm.cmd" set "NODE_DIR=%LocalAppData%\Programs\node"
if defined NODE_DIR (
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    set "PATH=%NODE_DIR%;%PATH%"
    exit /b 0
)
exit /b 1
