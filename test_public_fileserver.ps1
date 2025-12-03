# Testovaci skript pro verejny file server
Write-Host "========================================" -ForegroundColor Green
Write-Host "Test verejneho file serveru - /public/" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

$errors = 0
$warnings = 0

# 1. Kontrola slozky public_share
Write-Host "1. Kontrola slozky public_share..." -ForegroundColor Cyan
$publicDir = "$PSScriptRoot\public_share"
if (Test-Path $publicDir) {
    Write-Host "   ✅ Slozka public_share existuje: $publicDir" -ForegroundColor Green
    $files = Get-ChildItem $publicDir -File
    Write-Host "   Pocet souboru: $($files.Count)" -ForegroundColor Gray
    if ($files.Count -gt 0) {
        Write-Host "   Soubory:" -ForegroundColor Gray
        foreach ($file in $files) {
            Write-Host "     - $($file.Name) ($($file.Length) bytes)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "   ❌ Slozka public_share neexistuje" -ForegroundColor Red
    $errors++
}

# 2. Kontrola test.txt
Write-Host ""
Write-Host "2. Kontrola testovaciho souboru..." -ForegroundColor Cyan
$testFile = "$publicDir\test.txt"
if (Test-Path $testFile) {
    $content = Get-Content $testFile -Raw
    Write-Host "   ✅ test.txt existuje" -ForegroundColor Green
    Write-Host "   Obsah: $($content.Trim())" -ForegroundColor Gray
} else {
    Write-Host "   ⚠️  test.txt neexistuje" -ForegroundColor Yellow
    $warnings++
}

# 3. Test lokalniho serveru - /public/
Write-Host ""
Write-Host "3. Test lokalniho serveru - /public/..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/public/" -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ /public/ je dostupne lokalne (status: $($response.StatusCode))" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  /public/ odpovida, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  /public/ neni dostupne lokalne" -ForegroundColor Yellow
    Write-Host "      Server mozna potrebuje restart" -ForegroundColor Gray
    $warnings++
}

# 4. Test lokalniho serveru - konkretni soubor
Write-Host ""
Write-Host "4. Test lokalniho serveru - /public/test.txt..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/public/test.txt" -TimeoutSec 3 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ /public/test.txt je dostupne lokalne (status: $($response.StatusCode))" -ForegroundColor Green
        Write-Host "   Obsah: $($response.Content.Trim())" -ForegroundColor Gray
    } else {
        Write-Host "   ⚠️  /public/test.txt odpovida, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  /public/test.txt neni dostupne lokalne" -ForegroundColor Yellow
    Write-Host "      Server mozna potrebuje restart" -ForegroundColor Gray
    $warnings++
}

# 5. Test verejne URL - /public/
Write-Host ""
Write-Host "5. Test verejne URL - /public/..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/public/" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Verejny /public/ funguje! (status: $($response.StatusCode))" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Verejny /public/ odpovida, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  Verejny /public/ neni dostupny" -ForegroundColor Yellow
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    Write-Host "      Mozne priciny:" -ForegroundColor Gray
    Write-Host "      - Server nebezi" -ForegroundColor Gray
    Write-Host "      - Tunnel nebezi" -ForegroundColor Gray
    Write-Host "      - DNS problem" -ForegroundColor Gray
    $warnings++
}

# 6. Test verejne URL - konkretni soubor
Write-Host ""
Write-Host "6. Test verejne URL - /public/test.txt..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "https://hub.toozservis.cz/public/test.txt" -TimeoutSec 10 -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "   ✅ Verejny /public/test.txt funguje! (status: $($response.StatusCode))" -ForegroundColor Green
        Write-Host "   Obsah: $($response.Content.Trim())" -ForegroundColor Gray
        Write-Host ""
        Write-Host "   🔗 Verejny odkaz:" -ForegroundColor Cyan
        Write-Host "   https://hub.toozservis.cz/public/test.txt" -ForegroundColor White -BackgroundColor DarkBlue
    } else {
        Write-Host "   ⚠️  Verejny /public/test.txt odpovida, ale status: $($response.StatusCode)" -ForegroundColor Yellow
        $warnings++
    }
} catch {
    Write-Host "   ⚠️  Verejny /public/test.txt neni dostupny" -ForegroundColor Yellow
    Write-Host "      Chyba: $($_.Exception.Message)" -ForegroundColor Gray
    $warnings++
}

# Shrnutí
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Shrnuti" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($errors -eq 0 -and $warnings -eq 0) {
    Write-Host "✅ Vsechny testy prosly uspesne!" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Verejny file server je dostupny na:" -ForegroundColor Cyan
    Write-Host "   https://hub.toozservis.cz/public/" -ForegroundColor White -BackgroundColor DarkBlue
} elseif ($errors -eq 0) {
    Write-Host "⚠️  Testy prosly s varovanimi ($warnings)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "🌐 Verejny file server by mel byt dostupny na:" -ForegroundColor Cyan
    Write-Host "   https://hub.toozservis.cz/public/" -ForegroundColor White -BackgroundColor DarkBlue
} else {
    Write-Host "❌ Nalezeny chyby ($errors errors, $warnings warnings)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Dalsi kroky:" -ForegroundColor Cyan
if ($errors -gt 0) {
    Write-Host "  1. Opravte nalezene chyby vyse" -ForegroundColor White
}
if ($warnings -gt 0) {
    Write-Host "  2. Restartujte server: start_public_server.bat" -ForegroundColor White
    Write-Host "  3. Zkontrolujte tunnel: start_public_tunnel.bat" -ForegroundColor White
}
Write-Host "  4. Vlozte soubory do: public_share/" -ForegroundColor White
Write-Host "  5. Sdilejte odkazy: https://hub.toozservis.cz/public/NAZEV_SOUBORU" -ForegroundColor White
Write-Host ""
