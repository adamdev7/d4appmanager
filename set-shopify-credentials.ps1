# Paste Shopify Client ID and Secret into backend/.env (run once after creating Partner app)
# Usage: .\set-shopify-credentials.ps1

$envFile = Join-Path $PSScriptRoot "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "Copy backend\.env.example to backend\.env first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Shopify Partner app credentials" -ForegroundColor Cyan
Write-Host "  Get these from: https://partners.shopify.com -> Apps -> your app -> Client credentials"
Write-Host ""

$clientId = Read-Host "Client ID (API key)"
$clientSecret = Read-Host "Client secret" -AsSecureString
$plainSecret = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($clientSecret)
)

$content = Get-Content $envFile -Raw
$content = $content -replace "(?m)^SHOPIFY_CLIENT_ID=.*$", "SHOPIFY_CLIENT_ID=$clientId"
$content = $content -replace "(?m)^SHOPIFY_CLIENT_SECRET=.*$", "SHOPIFY_CLIENT_SECRET=$plainSecret"
Set-Content -Path $envFile -Value $content.TrimEnd()
Add-Content -Path $envFile -Value ""

Write-Host ""
Write-Host "  Saved. Next: .\configure-dev-tunnel.ps1  then restart API and connect a store." -ForegroundColor Green
Write-Host ""
