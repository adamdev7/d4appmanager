# One-time setup: venv + dependencies
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$launcher = if (Get-Command py -ErrorAction SilentlyContinue) { "py" }
            elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
            else { $null }

if (-not $launcher) {
    Write-Host "ERROR: Install Python from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

Write-Host "Creating virtual environment ..." -ForegroundColor Cyan
& $launcher -m venv (Join-Path $Root ".venv")

$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
Write-Host "Installing packages ..." -ForegroundColor Cyan
& $Pip install -r (Join-Path $Root "requirements.txt")

Write-Host ""
Write-Host "Setup complete. Start the server with:" -ForegroundColor Green
Write-Host "  .\run.ps1" -ForegroundColor White
Write-Host "  or  run.bat" -ForegroundColor White
