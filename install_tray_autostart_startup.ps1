# Instalace autostartu pro TooZ Hub 2 Tray aplikaci - Startup slozka
# Tato metoda nevyzaduje opravneni Administrator

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TooZ Hub 2 - Instalace autostartu" -ForegroundColor Cyan
Write-Host "(Startup slozka - bez opravneni Administrator)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Ziskat cestu k projektu
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = $scriptPath

# Najit start_toozhub_tray.bat
$batchFile = Join-Path $projectRoot "start_toozhub_tray.bat"

if (-not (Test-Path $batchFile)) {
    Write-Host "[CHYBA] Soubor $batchFile nebyl nalezen!" -ForegroundColor Red
    exit 1
}

# Startup slozka
$startupFolder = [System.Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "TooZ Hub 2 Tray.lnk"

Write-Host "[INFO] Startup slozka: $startupFolder" -ForegroundColor Cyan
Write-Host "[INFO] Zkratka: $shortcutPath" -ForegroundColor Cyan
Write-Host ""

# Vytvorit zkratku
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = $batchFile
    $Shortcut.WorkingDirectory = $projectRoot
    $Shortcut.Description = "TooZ Hub 2 Tray aplikace - automaticke spusteni serveru a tunelu"
    $Shortcut.Save()
    
    Write-Host "[OK] Zkratka uspesne vytvorena!" -ForegroundColor Green
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Instalace dokoncena!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Tray aplikace se nyni automaticky spusti pri kazdem prihlaseni do Windows." -ForegroundColor Green
    Write-Host ""
    Write-Host "Zkratka: $shortcutPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Pro odebrani autostartu smazte zkratku:" -ForegroundColor Yellow
    Write-Host "  Remove-Item '$shortcutPath'" -ForegroundColor White
    Write-Host ""
}
catch {
    Write-Host "[CHYBA] Chyba pri vytvareni zkratky: $_" -ForegroundColor Red
    exit 1
}




