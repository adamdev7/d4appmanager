# Expose local API (port 8000) via ngrok and set APP_URL in backend/.env
# Run from project root:  .\configure-dev-tunnel.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$envFile = Join-Path $root "backend\.env"

function Get-NgrokExe {
    # Refresh PATH (winget installs may not be visible until shell restart)
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"

    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\ngrok.exe"
        "$env:ProgramFiles\ngrok\ngrok.exe"
        "$env:LOCALAPPDATA\Programs\ngrok\ngrok.exe"
    )

    $wingetRoot = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
    if (Test-Path $wingetRoot) {
        $found = Get-ChildItem -Path $wingetRoot -Recurse -Filter "ngrok.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($found) { $candidates = @($found) + $candidates }
    }

    foreach ($p in $candidates) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}

function Get-NgrokPublicUrl {
    try {
        $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2
        foreach ($t in $tunnels.tunnels) {
            if ($t.public_url -match '^https://') {
                return $t.public_url.TrimEnd('/')
            }
        }
    }
    catch {
        # ngrok not running yet
    }
    return $null
}

function Set-AppUrlInEnv {
    param([string]$Url)

    if (-not (Test-Path $envFile)) {
        Write-Host "Missing $envFile - copy backend\.env.example to backend\.env first." -ForegroundColor Red
        exit 1
    }

    $lines = Get-Content $envFile -Raw
    $pattern = '(?m)^APP_URL=.*$'
    $replacement = 'APP_URL=' + $Url
    if ($lines -match $pattern) {
        $lines = $lines -replace $pattern, $replacement
    }
    else {
        $lines = $replacement + "`n" + $lines
    }
    Set-Content -Path $envFile -Value $lines.TrimEnd() -NoNewline
    Add-Content -Path $envFile -Value ""
}

Write-Host ""
Write-Host "  App Manager - dev tunnel setup" -ForegroundColor Cyan
Write-Host "  --------------------------------" -ForegroundColor Cyan
Write-Host ""

$ngrok = Get-NgrokExe
if (-not $ngrok) {
    Write-Host "ngrok not found. Install: winget install Ngrok.Ngrok" -ForegroundColor Red
    Write-Host "Then run: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
}

# ngrok free accounts require agent 3.20+ (winget may install an old build)
$verLine = & $ngrok version 2>&1 | Select-Object -First 1
if ($verLine -match '(\d+)\.(\d+)') {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 20)) {
        Write-Host "Updating ngrok (installed version is too old for your account)..." -ForegroundColor Yellow
        & $ngrok update 2>&1 | Out-Null
    }
}

$url = Get-NgrokPublicUrl
if (-not $url) {
    Write-Host "Starting ngrok on port 8000 (new window)..." -ForegroundColor Yellow
    Write-Host "Make sure the API is running (start-dev.bat or backend\start.bat)." -ForegroundColor Yellow
    Start-Process -FilePath $ngrok -ArgumentList "http", "8000"
    Write-Host "Waiting for tunnel (up to 60s)..."
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        $url = Get-NgrokPublicUrl
        if ($url) { break }
    }
}

if (-not $url) {
    Write-Host "Could not get ngrok URL." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Checklist:" -ForegroundColor Yellow
    Write-Host "  1. Run start-dev.bat FIRST (API must listen on port 8000)"
    Write-Host "  2. In the ngrok window, confirm it shows 'online' with an https URL"
    Write-Host "  3. Or run manually:  ngrok http 8000"
    Write-Host "  4. Auth token:  ngrok config add-authtoken YOUR_TOKEN"
    Write-Host "  5. Old ngrok? Run:  ngrok update   (need 3.20+)"
    Write-Host ""
    Write-Host "  Then run this script again (or copy the https URL from ngrok into Shopify + .env APP_URL)"
    exit 1
}

Set-AppUrlInEnv -Url $url

Write-Host ""
Write-Host "  Public API URL:  $url" -ForegroundColor Green
Write-Host ""
Write-Host "  Set these in Shopify Partners (Apps -> your app -> Configuration):" -ForegroundColor White
Write-Host "    App URL:                  $url"
Write-Host "    Allowed redirection URL:  $url/api/v1/stores/shopify/callback"
Write-Host ""
Write-Host "  Updated backend\.env APP_URL. Restart the API window, then connect a store in the UI."
Write-Host ""
