# App Manager — start FastAPI (PowerShell)
# Usage:  cd backend
#         .\run.ps1

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"

function Find-PyLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { return "python3" }
    return $null
}

if (-not (Test-Path $Python)) {
    Write-Host "Virtual environment not found. Creating .venv ..." -ForegroundColor Yellow
    $launcher = Find-PyLauncher
    if (-not $launcher) {
        Write-Host "ERROR: Python is not installed or not on PATH." -ForegroundColor Red
        Write-Host "Install from https://www.python.org/downloads/ and enable 'Add to PATH'." -ForegroundColor Red
        exit 1
    }
    & $launcher -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $Python)) {
        Write-Host "ERROR: Failed to create .venv" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path (Join-Path $Root ".venv\Scripts\uvicorn.exe"))) {
    Write-Host "Installing dependencies ..." -ForegroundColor Yellow
    & $Pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: pip install failed" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "  App Manager API" -ForegroundColor Green
Write-Host "  http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "  Docs: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host ""

& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
