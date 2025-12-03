# PowerShell skript pro instalaci Cloudflare Tunnel jako Windows služby
# Vyžaduje NSSM (Non-Sucking Service Manager)

Write-Host "========================================" -ForegroundColor Green
Write-Host "Instalace Cloudflare Tunnel služby" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# Zkontrolovat, zda je NSSM nainstalován
$nssmPath = "C:\Program Files\nssm\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Host "❌ NSSM není nainstalován!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Nainstalujte NSSM z:" -ForegroundColor Yellow
    Write-Host "  https://nssm.cc/download" -ForegroundColor White
    Write-Host ""
    Write-Host "Nebo použijte winget:" -ForegroundColor Yellow
    Write-Host "  winget install NSSM.NSSM" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Zkontrolovat, zda cloudflared existuje
$cloudflaredPath = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflaredPath) {
    Write-Host "❌ cloudflared není v PATH!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Nainstalujte cloudflared:" -ForegroundColor Yellow
    Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "✅ NSSM nalezen: $nssmPath" -ForegroundColor Green
Write-Host "✅ cloudflared nalezen: $cloudflaredPath" -ForegroundColor Green
Write-Host ""

# Zkontrolovat, zda služba už existuje
$service = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
if ($service) {
    Write-Host "⚠️  Služba 'cloudflared' již existuje!" -ForegroundColor Yellow
    $response = Read-Host "Chcete ji přeinstalovat? (y/n)"
    if ($response -ne "y") {
        Write-Host "Instalace zrušena." -ForegroundColor Yellow
        exit 0
    }
    Write-Host "Odstraňuji starou službu..." -ForegroundColor Yellow
    & $nssmPath remove cloudflared confirm
    Start-Sleep -Seconds 2
}

# Získat cestu k projektu
$projectPath = $PSScriptRoot
Write-Host "Cesta k projektu: $projectPath" -ForegroundColor Cyan
Write-Host ""

# Instalovat službu
Write-Host "Instaluji službu..." -ForegroundColor Yellow
& $nssmPath install cloudflared "$cloudflaredPath" "tunnel run tooz-hub2"
& $nssmPath set cloudflared AppDirectory "$projectPath"
& $nssmPath set cloudflared DisplayName "Cloudflare Tunnel - TooZ Hub 2"
& $nssmPath set cloudflared Description "Cloudflare Tunnel pro TooZ Hub 2 (hub.toozservis.cz)"
& $nssmPath set cloudflared Start SERVICE_AUTO_START

Write-Host ""
Write-Host "✅ Služba byla nainstalována!" -ForegroundColor Green
Write-Host ""

# Spustit službu
$response = Read-Host "Chcete službu nyní spustit? (y/n)"
if ($response -eq "y") {
    Write-Host "Spouštím službu..." -ForegroundColor Yellow
    Start-Service cloudflared
    Start-Sleep -Seconds 2
    
    $service = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    if ($service.Status -eq "Running") {
        Write-Host "✅ Služba je spuštěna!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Služba se nespustila. Zkontrolujte logy:" -ForegroundColor Yellow
        Write-Host "   Get-EventLog -LogName Application -Source cloudflared -Newest 10" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Instalace dokončena!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Užitečné příkazy:" -ForegroundColor Cyan
Write-Host "  Start-Service cloudflared      - Spustit službu" -ForegroundColor White
Write-Host "  Stop-Service cloudflared       - Zastavit službu" -ForegroundColor White
Write-Host "  Get-Service cloudflared        - Zobrazit status" -ForegroundColor White
Write-Host "  & '$nssmPath' remove cloudflared confirm  - Odstranit službu" -ForegroundColor White
Write-Host ""

