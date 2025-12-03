# 🔄 Aktualizace Cloudflared

## ✅ Co bylo provedeno

1. ✅ Záloha tunelových souborů vytvořena
2. ✅ Cloudflared stažen (65.44 MB)
3. ✅ Tunelové soubory zkontrolovány a obnoveny

## ⚠️ Aktualizace vyžaduje admin práva

Cloudflared je nainstalován v `C:\Program Files\cloudflared\` a aktualizace vyžaduje oprávnění správce.

## 🚀 Jak aktualizovat (vyberte jednu z možností)

### Možnost 1: Winget (doporučeno)

Otevřete PowerShell jako správce a spusťte:

```powershell
winget upgrade Cloudflare.cloudflared
```

### Možnost 2: Manuální kopírování

1. Otevřete PowerShell jako správce
2. Spusťte:

```powershell
$downloadedExe = "C:\Projects\TOOZHUB2\cloudflared-latest.exe"
$targetPath = "C:\Program Files\cloudflared\cloudflared.exe"
Copy-Item $downloadedExe -Destination $targetPath -Force
```

### Možnost 3: Použití staženého MSI

Pokud máte stažený MSI soubor:

```powershell
# Jako správce
msiexec /i cloudflared-latest.msi /quiet /qn /norestart
```

## ✅ Ověření po aktualizaci

Po aktualizaci ověřte:

```powershell
cloudflared --version
```

Měli byste vidět: `cloudflared version 2025.11.1` nebo novější.

## 🔒 Tunelové soubory

- ✅ **Záloha vytvořena** v: `C:\Users\djtoo\.cloudflared\backup_YYYYMMDD_HHMMSS\`
- ✅ **Config.yml** existuje a je správně nastaven
- ✅ **Credentials file** existuje: `a8451dbb-2ca2-4006-862b-09959b274eb4.json`

## 🧪 Test po aktualizaci

Po aktualizaci restartujte tunnel:

```bash
start_public_tunnel.bat
```

A otestujte:

```powershell
.\test_public_access.ps1
```

## 📝 Poznámky

- Aktualizace cloudflared **NEMÁ** vymazat tunelové soubory
- Záloha byla vytvořena pro jistotu
- Pokud by nějaké soubory chyběly, jsou obnoveny ze zálohy

---

**Stažený cloudflared:** `C:\Projects\TOOZHUB2\cloudflared-latest.exe`  
**Záloha souborů:** `C:\Users\djtoo\.cloudflared\backup_YYYYMMDD_HHMMSS\`

