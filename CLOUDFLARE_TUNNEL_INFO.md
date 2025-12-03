# 🔗 Cloudflare Tunnel - Informace

## ✅ Tunnel je spuštěný!

Cloudflare Tunnel běží na pozadí a vytváří veřejný přístup k vašemu serveru.

## 📍 Jak získat veřejnou URL

### Metoda 1: Zkontrolujte výstup v terminálu

V terminálu, kde běží tunnel, byste měli vidět výstup podobný:

```
+--------------------------------------------------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable): |
|  https://xxxxx-xxxxx-xxxxx.trycloudflare.com                                               |
+--------------------------------------------------------------------------------------------+
```

### Metoda 2: Otevřete nový terminál a zkontrolujte procesy

```powershell
# Zobrazit běžící cloudflared procesy
Get-Process cloudflared -ErrorAction SilentlyContinue
```

### Metoda 3: Zkontrolujte výstup v původním terminálu

Cloudflare Tunnel obvykle zobrazuje URL přímo v terminálu při startu.

## 🔗 Jak používat URL

Jakmile máte URL (např. `https://xxxxx.trycloudflare.com`), můžete ji použít:

### File Browser:
```
https://xxxxx.trycloudflare.com/files/
```

### API Docs:
```
https://xxxxx.trycloudflare.com/docs
```

### Health Check:
```
https://xxxxx.trycloudflare.com/health
```

## 📤 Pro sdílení s ChatGPT

Sdílejte tuto URL:
```
https://xxxxx.trycloudflare.com/files/
```

ChatGPT pak může:
- Prohlížet strukturu projektu přes web rozhraní
- Používat JSON API: `https://xxxxx.trycloudflare.com/files/api/list`
- Stahovat soubory: `https://xxxxx.trycloudflare.com/files/download?path=...`

## ⚠️ Důležité poznámky

1. **Tunnel běží pouze dokud je spuštěný** - pokud zavřete terminál nebo ukončíte proces, tunnel se ukončí
2. **URL je dočasná** - při každém novém spuštění dostanete novou URL
3. **Bezpečnost** - URL je veřejně přístupná, ale bez dalších bezpečnostních opatření

## 🛑 Zastavení tunelu

Pro zastavení tunelu:
```powershell
# Najít proces
Get-Process cloudflared

# Ukončit proces
Stop-Process -Name cloudflared
```

Nebo jednoduše zavřete terminál, kde tunnel běží.

## 🔄 Restart tunelu

Pokud potřebujete restartovat tunel:

1. Zastavte aktuální tunnel
2. Spusťte znovu:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8001
   ```

---

**Vytvořeno:** 2025-01-27

