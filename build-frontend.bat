@echo off
cd /d "%~dp0"

call :find_node
if not defined NPM_CMD (
    echo ERROR: Install Node.js LTS from https://nodejs.org/
    pause
    exit /b 1
)

if exist "frontend\node_modules\npm" (
    echo Run fix-frontend.bat first.
    pause
    exit /b 1
)

echo Building frontend...
cd frontend
if not exist "node_modules\vite" call "%NPM_CMD%" install
call "%NPM_CMD%" run build
if errorlevel 1 exit /b 1

echo.
echo Done. Restart the backend and open http://127.0.0.1:8000
pause
exit /b 0

:find_node
set "NPM_CMD="
set "NODE_DIR="
if exist "%ProgramFiles%\nodejs\npm.cmd" set "NODE_DIR=%ProgramFiles%\nodejs"
if not defined NODE_DIR if exist "%LocalAppData%\Programs\node\npm.cmd" set "NODE_DIR=%LocalAppData%\Programs\node"
if defined NODE_DIR (
    set "NPM_CMD=%NODE_DIR%\npm.cmd"
    set "PATH=%NODE_DIR%;%PATH%"
    exit /b 0
)
exit /b 1
