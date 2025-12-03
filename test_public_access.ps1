# Testovací skript pro veřejný přístup
Write-Host "========================================" -ForegroundColor Green
Write-Host "Test veřejného přístupu - hub.toozservis.cz" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

$errors = 0
$warnings = 0

# 1. Test lokálního serveru
Write-Host "1. Test lokálního serveru (localhost:8000)..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Server běží lokálně (status: $($response.StatusCode))" -ForegroundColor Green
        $content = $response.Content | ConvertFrom-Json
        Write-Host "      Service: $($content.service)" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  Server odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ❌ Server neběží na localhost:8000" -ForegroundColor Red
    Write-Host "      Spusťte: start_public_server.bat" -ForegroundColor Gray
    $errors++
}

# 2. Test /web/index.html lokálně
Write-Host ""
Write-Host "2. Test /web/index.html lokálně..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/web/index.html" -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ /web/index.html je dostupné lokálně" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  /web/index.html odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ❌ /web/index.html není dostupné lokálně" -ForegroundColor Red
    $errors++
}

# 3. Kontrola tunnel procesu
Write-Host ""
Write-Host "3. Kontrola Cloudflare Tunnel procesu..." -ForegroundColor Cyan
$tunnelProcess = Get-Process cloudflared -ErrorAction SilentlyContinue
if ($tunnelProcess) {
    Write-Host "   ✅ Cloudflared proces běží (ID: $($tunnelProcess[0].Id))" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Cloudflared proces neběží" -ForegroundColor Yellow
    Write-Host "      Spusťte: start_public_tunnel.bat" -ForegroundColor Gray
    $warnings++
}

# 4. Test veřejné URL - health
Write-Host ""
Write-Host "4. Test veřejné URL - /health..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/health" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Veřejná URL funguje! (status: $($response.StatusCode))" -ForegroundColor Green
        $content = $response.Content | ConvertFrom-Json
        Write-Host "      Service: $($content.service)" -ForegroundColor Gray
        Write-Host "      Version: $($content.version)" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  Veřejná URL odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ❌ Veřejná URL není dostupná" -ForegroundColor Red
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "      Možné příčiny:" -ForegroundColor Yellow
    Write-Host "      - DNS záznam není nastaven (zkontrolujte DNS_KONTROLA.md)" -ForegroundColor Gray
    Write-Host "      - DNS ještě nepropagovalo (počkejte 5-10 minut)" -ForegroundColor Gray
    Write-Host "      - Tunnel neběží" -ForegroundColor Gray
    $errors++
}

# 5. Test veřejné URL - /web/index.html
Write-Host ""
Write-Host "5. Test veřejné URL - /web/index.html..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/web/index.html" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Veřejný File Browser funguje! (status: $($response.StatusCode))" -ForegroundColor Green
        Write-Host "      Velikost: $($response.Content.Length) bytů" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  Veřejný File Browser odpovídá, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ❌ Veřejný File Browser není dostupný" -ForegroundColor Red
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    $warnings++
}

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Shrnutí" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($errors -eq 0 -and $warnings -eq 0) {
    Write-Host "✅ Všechny testy prošly úspěšně!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Veřejný odkaz pro sdílení:" -ForegroundColor Cyan
    Write-Host "   https://hub.toozservis.cz/web/index.html" -ForegroundColor White -BackgroundColor DarkBlue
} elseif ($errors -eq 0) {
    Write-Host "⚠️  Testy prošly s varováními ($warnings)" -ForegroundColor Yellow
} else {
    Write-Host "❌ Nalezeny chyby ($errors chyb, $warnings varování)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Další kroky:" -ForegroundColor Cyan
if ($errors -gt 0) {
    Write-Host "  1. Opravte nalezené chyby výše" -ForegroundColor White
}
if ($warnings -gt 0) {
    Write-Host "  2. Zkontrolujte varování" -ForegroundColor White
}
Write-Host "  3. Zkontrolujte DNS: DNS_KONTROLA.md" -ForegroundColor White
Write-Host ""

