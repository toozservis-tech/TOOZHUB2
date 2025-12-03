# Skript pro bezpečnou aktualizaci cloudflared
# Tento skript zastaví běžící tunnel, aktualizuje cloudflared a obnoví tunnel

Write-Host "========================================" -ForegroundColor Green
Write-Host "Aktualizace Cloudflared" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 1. Zastavit všechny cloudflared procesy
Write-Host "1. Zastavuji běžící cloudflared procesy..." -ForegroundColor Cyan
$processes = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($processes) {
    Write-Host "   Nalezeny běžící procesy: $($processes.Count)" -ForegroundColor Yellow
    foreach ($proc in $processes) {
        Write-Host "   Zastavuji proces ID: $($proc.Id)" -ForegroundColor Gray
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Write-Host "   ✅ Všechny procesy zastaveny" -ForegroundColor Green
} else {
    Write-Host "   ✅ Žádné běžící procesy" -ForegroundColor Green
}

# 2. Záloha tunelových souborů
Write-Host ""
Write-Host "2. Vytvářím zálohu tunelových souborů..." -ForegroundColor Cyan
$cloudflaredDir = "$env:USERPROFILE\.cloudflared"
$backupDir = "$cloudflaredDir\backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
if (Test-Path $cloudflaredDir) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Copy-Item "$cloudflaredDir\*.json" -Destination $backupDir -ErrorAction SilentlyContinue
    Copy-Item "$cloudflaredDir\*.yml" -Destination $backupDir -ErrorAction SilentlyContinue
    Write-Host "   ✅ Záloha vytvořena: $backupDir" -ForegroundColor Green
}

# 3. Získat aktuální umístění cloudflared
Write-Host ""
Write-Host "3. Zjišťuji umístění cloudflared..." -ForegroundColor Cyan
$cloudflaredCmd = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cloudflaredCmd) {
    $currentPath = $cloudflaredCmd.Source
    Write-Host "   ✅ Cloudflared nalezen: $currentPath" -ForegroundColor Green
    
    # 4. Zkontrolovat stažený soubor
    Write-Host ""
    Write-Host "4. Kontroluji stažený cloudflared..." -ForegroundColor Cyan
    $downloadedExe = "$PSScriptRoot\cloudflared-latest.exe"
    if (Test-Path $downloadedExe) {
        Write-Host "   ✅ Stažený soubor existuje: $downloadedExe" -ForegroundColor Green
        
        # 5. Záloha starého cloudflared
        Write-Host ""
        Write-Host "5. Zálohuji starý cloudflared..." -ForegroundColor Cyan
        $backupExe = "$currentPath.backup"
        Copy-Item $currentPath -Destination $backupExe -Force -ErrorAction SilentlyContinue
        Write-Host "   ✅ Záloha vytvořena: $backupExe" -ForegroundColor Green
        
        # 6. Aktualizovat cloudflared
        Write-Host ""
        Write-Host "6. Aktualizuji cloudflared..." -ForegroundColor Cyan
        try {
            Copy-Item $downloadedExe -Destination $currentPath -Force
            Start-Sleep -Seconds 1
            Write-Host "   ✅ Cloudflared aktualizován" -ForegroundColor Green
        } catch {
            Write-Host "   ❌ Chyba při aktualizaci: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "   Zkuste spustit PowerShell jako správce" -ForegroundColor Yellow
            exit 1
        }
        
        # 7. Ověřit novou verzi
        Write-Host ""
        Write-Host "7. Ověřuji novou verzi..." -ForegroundColor Cyan
        Start-Sleep -Seconds 1
        $version = & $currentPath --version 2>&1
        Write-Host "   Verze: $version" -ForegroundColor White
        if ($version -match "2025.11") {
            Write-Host "   ✅ Aktualizace úspěšná na 2025.11.x!" -ForegroundColor Green
        } elseif ($version -match "2025") {
            Write-Host "   ⚠️  Verze je z roku 2025, ale může být stále stará" -ForegroundColor Yellow
        }
        
    } else {
        Write-Host "   ❌ Stažený soubor neexistuje: $downloadedExe" -ForegroundColor Red
        Write-Host "   Stáhněte nejnovější verzi z GitHub" -ForegroundColor Yellow
    }
} else {
    Write-Host "   ❌ Cloudflared není v PATH" -ForegroundColor Red
    exit 1
}

# 8. Ověřit tunelové soubory
Write-Host ""
Write-Host "8. Ověřuji tunelové soubory..." -ForegroundColor Cyan
$configPath = "$cloudflaredDir\config.yml"
$credentialsPath = "$cloudflaredDir\a8451dbb-2ca2-4006-862b-09959b274eb4.json"
if (Test-Path $configPath) {
    Write-Host "   ✅ config.yml existuje" -ForegroundColor Green
} else {
    Write-Host "   ❌ config.yml chybí" -ForegroundColor Red
}
if (Test-Path $credentialsPath) {
    Write-Host "   ✅ credentials file existuje" -ForegroundColor Green
} else {
    Write-Host "   ❌ credentials file chybí" -ForegroundColor Red
}

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Aktualizace dokončena!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Další kroky:" -ForegroundColor Cyan
Write-Host "  1. Restartujte tunnel: start_public_tunnel.bat" -ForegroundColor White
Write-Host "  2. Otestujte: .\test_public_access.ps1" -ForegroundColor White
Write-Host ""

