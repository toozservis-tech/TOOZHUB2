# Testovací skript pro ověření Cloudflare Tunnel nastavení

Write-Host "========================================" -ForegroundColor Green
Write-Host "Test Cloudflare Tunnel nastavení" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

$errors = 0
$warnings = 0

# 1. Zkontrolovat, zda server běží
Write-Host "1. Kontrola serveru na localhost:8000..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Server běží (status: $($response.StatusCode))" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Server odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ❌ Server neběží nebo není dostupný" -ForegroundColor Red
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    $errors++
}

# 2. Zkontrolovat, zda cloudflared je nainstalován
Write-Host ""
Write-Host "2. Kontrola cloudflared..." -ForegroundColor Cyan
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cloudflared) {
    Write-Host "   ✅ cloudflared nalezen: $($cloudflared.Source)" -ForegroundColor Green
    $version = & cloudflared --version 2>&1
    Write-Host "      Verze: $version" -ForegroundColor Gray
} else {
    Write-Host "   ❌ cloudflared není v PATH" -ForegroundColor Red
    $errors++
}

# 3. Zkontrolovat, zda tunnel existuje
Write-Host ""
Write-Host "3. Kontrola tunelu 'tooz-hub2'..." -ForegroundColor Cyan
try {
    $tunnels = & cloudflared tunnel list 2>&1
    if ($tunnels -match "tooz-hub2") {
        Write-Host "   ✅ Tunnel 'tooz-hub2' existuje" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Tunnel 'tooz-hub2' nebyl nalezen" -ForegroundColor Yellow
        Write-Host "      Spusťte: cloudflared tunnel create tooz-hub2" -ForegroundColor Gray
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  Nelze zkontrolovat tunely: $($_.Exception.Message)" -ForegroundColor Yellow
    $warnings++
}

# 4. Zkontrolovat credentials soubor
Write-Host ""
Write-Host "4. Kontrola credentials souboru..." -ForegroundColor Cyan
$credentialsPath = "$env:USERPROFILE\.cloudflared\tooz-hub2.json"
if (Test-Path $credentialsPath) {
    Write-Host "   ✅ Credentials soubor existuje: $credentialsPath" -ForegroundColor Green
} else {
    Write-Host "   ❌ Credentials soubor neexistuje: $credentialsPath" -ForegroundColor Red
    Write-Host "      Vytvořte tunnel: cloudflared tunnel create tooz-hub2" -ForegroundColor Gray
    $errors++
}

# 5. Zkontrolovat config.yml
Write-Host ""
Write-Host "5. Kontrola config.yml..." -ForegroundColor Cyan
$configPath = "$PSScriptRoot\cloudflared\config.yml"
if (Test-Path $configPath) {
    Write-Host "   ✅ config.yml existuje: $configPath" -ForegroundColor Green
    $config = Get-Content $configPath -Raw
    if ($config -match "tunnel: tooz-hub2") {
        Write-Host "   ✅ Tunnel název je správný" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Tunnel název v config.yml neodpovídá" -ForegroundColor Yellow
        $warnings++
    }
    if ($config -match "hub.toozservis.cz") {
        Write-Host "   ✅ Hostname je správný (hub.toozservis.cz)" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Hostname v config.yml není správný" -ForegroundColor Yellow
        $warnings++
    }
} else {
    Write-Host "   ❌ config.yml neexistuje: $configPath" -ForegroundColor Red
    $errors++
}

# 6. Zkontrolovat, zda tunnel proces běží
Write-Host ""
Write-Host "6. Kontrola běžících tunnel procesů..." -ForegroundColor Cyan
$tunnelProcesses = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($tunnelProcesses) {
    Write-Host "   ✅ Cloudflared proces běží (ID: $($tunnelProcesses[0].Id))" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Cloudflared proces neběží" -ForegroundColor Yellow
    Write-Host "      Spusťte: start_cloudflare_tunnel.bat" -ForegroundColor Gray
    $warnings++
}

# 7. Test veřejné URL
Write-Host ""
Write-Host "7. Test veřejné URL (hub.toozservis.cz)..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/health" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Veřejná URL funguje (status: $($response.StatusCode))" -ForegroundColor Green
        $content = $response.Content | ConvertFrom-Json
        Write-Host "      Service: $($content.service)" -ForegroundColor Gray
        Write-Host "      Version: $($content.version)" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  Veřejná URL odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  Veřejná URL není dostupná" -ForegroundColor Yellow
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    Write-Host "      Možné příčiny:" -ForegroundColor Gray
    Write-Host "      - DNS ještě nepropagovalo (počkejte 5-10 minut)" -ForegroundColor Gray
    Write-Host "      - Tunnel neběží" -ForegroundColor Gray
    Write-Host "      - DNS záznam není správně nastaven" -ForegroundColor Gray
    $warnings++
}

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Shrnutí" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($errors -eq 0 -and $warnings -eq 0) {
    Write-Host "✅ Všechny kontroly prošly úspěšně!" -ForegroundColor Green
} elseif ($errors -eq 0) {
    Write-Host "⚠️  Kontroly prošly s varováními ($warnings)" -ForegroundColor Yellow
} else {
    Write-Host "❌ Nalezeny chyby ($errors chyb, $warnings varování)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Další kroky:" -ForegroundColor Cyan
if ($errors -gt 0) {
    Write-Host "  1. Opravte nalezené chyby" -ForegroundColor White
}
if ($warnings -gt 0) {
    Write-Host "  2. Zkontrolujte varování" -ForegroundColor White
}
Write-Host "  3. Spusťte test znovu: .\test_cloudflare_tunnel.ps1" -ForegroundColor White
Write-Host ""

