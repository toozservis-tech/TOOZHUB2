# scripts/windows/run_tunnel.ps1
# Spuštění Cloudflare Tunnel pro TOOZHUB2

# UPRAV tyto hodnoty podle projektu:
$tunnelName = "tooz-hub2"      # Název tunelu v Cloudflare
$hostname = "hub.toozservis.cz"      # Veřejná doména

# Nastavit working directory na root projektu
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $projectRoot

# Zkontrolovat, zda je cloudflared nainstalován
$cloudflaredExe = "cloudflared"
if (-not (Get-Command $cloudflaredExe -ErrorAction SilentlyContinue)) {
    Write-Host "CHYBA: cloudflared.exe nebyl nalezen v PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Instalujte cloudflared:"
    Write-Host "1. Stáhněte z: https://github.com/cloudflare/cloudflared/releases"
    Write-Host "2. Nebo použijte: winget install --id Cloudflare.cloudflared"
    Write-Host ""
    Write-Host "Ujistěte se, že máte vytvořený tunel:"
    Write-Host "  cloudflared tunnel create $tunnelName"
    Write-Host "  cloudflared tunnel route dns $tunnelName $hostname"
    exit 1
}

# Zkontrolovat, zda existuje config soubor
$configFile = Join-Path $projectRoot "cloudflared\config.yml"
if (-not (Test-Path $configFile)) {
    $configFile = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    if (-not (Test-Path $configFile)) {
        Write-Host "CHYBA: Config soubor neexistuje!" -ForegroundColor Red
        Write-Host "Očekávané umístění:"
        Write-Host "  - $projectRoot\cloudflared\config.yml"
        Write-Host "  - $configFile"
        exit 1
    }
}

# Spuštění cloudflared tunnel s explicitním config souborem
Start-Process $cloudflaredExe -ArgumentList @(
    "tunnel",
    "--config", $configFile,
    "run", $tunnelName
) -WindowStyle Minimized

Write-Host "Cloudflare Tunnel spuštěn: $tunnelName -> $hostname"
Write-Host "Config soubor: $configFile"
Write-Host "Pro zastavení použijte Task Manager nebo: Get-Process cloudflared | Stop-Process"

