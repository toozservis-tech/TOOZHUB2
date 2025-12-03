# 🌐 Veřejný přístup k souborům projektu

## ✅ Cloudflare Tunnel je aktivní!

Server je nyní přístupný z jakékoli sítě přes Cloudflare Tunnel.

## 🔗 Veřejná URL

### File Browser (pro ChatGPT):
```
[URL se zobrazí po inicializaci tunelu]
```

### Ostatní endpointy:
- **API Docs**: `[URL]/docs`
- **Health Check**: `[URL]/health`
- **JSON API**: `[URL]/files/api/list`

## 📋 Jak používat

### Pro ChatGPT - sdílejte tuto URL:
```
[URL]/files/
```

ChatGPT pak může:
1. Prohlížet strukturu projektu přes web rozhraní
2. Používat JSON API pro automatizované získání souborů
3. Stahovat jednotlivé soubory

### Příklad použití pro ChatGPT:

```
Soubory projektu jsou dostupné na:
[URL]/files/

Pro získání struktury projektu:
GET [URL]/files/api/list

Pro zobrazení souboru:
GET [URL]/files/view?path=src/server/main.py

Pro stažení souboru:
GET [URL]/files/download?path=src/server/main.py
```

## ⚠️ Důležité poznámky

1. **Tunnel běží pouze dokud je spuštěný** - pokud ukončíte proces cloudflared, tunnel se ukončí
2. **URL se může změnit** - při každém restartu tunelu dostanete novou URL
3. **Dočasný přístup** - Cloudflare Tunnel bez účtu je dočasný a může být kdykoli ukončen
4. **Bezpečnost** - URL je veřejně přístupná, citlivé soubory (`.env`, databáze) jsou automaticky skryty

## 🛑 Zastavení veřejného přístupu

Pro zastavení veřejného přístupu:

```powershell
# Najít a zastavit cloudflared proces
Get-Process cloudflared | Stop-Process -Force
```

## 🔄 Obnovení URL

Pokud potřebujete novou URL:

1. Zastavte starý tunnel
2. Spusťte znovu:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8001
   ```
3. URL se zobrazí v terminálu

---

**Vytvořeno:** 2025-01-27  
**Účel:** Veřejný přístup k souborům projektu pro kontrolu ChatGPT

