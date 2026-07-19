@echo off
REM Fix broken npm / node_modules (run once if npm install fails)
cd /d "%~dp0"

call :find_node
if not defined NPM_CMD (
    echo ERROR: Install Node.js LTS from https://nodejs.org/ then reopen the terminal.
    pause
    exit /b 1
)

echo Using: %NPM_CMD%
echo.

if exist "frontend\node_modules" (
    echo Removing broken frontend\node_modules ...
    rmdir /s /q "frontend\node_modules"
)

if exist "frontend\package-lock.json" del "frontend\package-lock.json"

echo Installing frontend dependencies...
cd frontend
call "%NPM_CMD%" install
if errorlevel 1 (
    echo.
    echo Install failed. Try: close terminal, reopen, run this script again.
    cd ..
    pause
    exit /b 1
)

cd ..
echo.
echo Success. Run:  .\start-dev.bat
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
