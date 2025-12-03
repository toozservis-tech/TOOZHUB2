# Odebrani autostartu pro TooZ Hub 2 Tray aplikaci

$taskName = "TooZHub2-Tray"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TooZ Hub 2 - Odebrani autostartu" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Zkontrolovat, jestli ukol existuje
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if (-not $existingTask) {
    Write-Host "[VAROVANI] Ukol '$taskName' neexistuje." -ForegroundColor Yellow
    exit 0
}

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    
    Write-Host "[OK] Ukol '$taskName' byl uspesne odebran!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Tray aplikace se uz nebude automaticky spoustet pri prihlaseni." -ForegroundColor Yellow
    Write-Host ""
}
catch {
    Write-Host "[CHYBA] Chyba pri odebirani ukolu: $_" -ForegroundColor Red
    exit 1
}
