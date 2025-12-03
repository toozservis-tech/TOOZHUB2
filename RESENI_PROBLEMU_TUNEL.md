# 🔧 Řešení problému s Cloudflare Tunnel

## Problém
Cloudflare Tunnel URL není dostupná nebo nefunguje.

## Možná řešení

### 1. ✅ Zkontrolujte lokální server

Nejprve otevřete v prohlížeči:
```
http://127.0.0.1:8001/files/
```

Pokud to funguje lokálně, server běží správně a problém je s tunelem.

### 2. 🔄 Restartujte Cloudflare Tunnel

Pokud tunnel nefunguje:
1. Zavřete všechna okna s cloudflared
2. Spusťte nový tunnel:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8001
   ```
3. Počkejte 5-10 sekund na inicializaci
4. Zkopírujte novou URL z terminálu

### 3. 🌐 Alternativní řešení - Použít lokální IP (HOST=0.0.0.0)

Pokud tunnel stále nefunguje, můžete použít lokální síť:

#### Krok 1: Zjistěte vaši lokální IP adresu
```powershell
ipconfig | findstr IPv4
```

#### Krok 2: Změňte HOST v .env souboru
Vytvořte nebo upravte `.env` soubor:
```
HOST=0.0.0.0
PORT=8001
```

#### Krok 3: Restartujte server
```bash
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8001
```

#### Krok 4: Otevřete z jiného zařízení v lokální síti
```
http://[VAŠE_LOKÁLNÍ_IP]:8001/files/
```
Např.: `http://192.168.1.100:8001/files/`

**Poznámka:** Toto bude fungovat pouze v lokální síti, ne z internetu.

### 4. 🔍 Zkontrolujte firewall

Windows Firewall může blokovat připojení:

1. Otevřete Windows Defender Firewall
2. Povolte Python a cloudflared v pravidlech

### 5. 📝 Otestujte server ručně

#### Zkontrolujte, že server běží:
```powershell
curl http://127.0.0.1:8001/health
```

#### Zkontrolujte file browser:
```powershell
curl http://127.0.0.1:8001/files/
```

### 6. 🛠️ Debugging

#### Zkontrolujte běžící procesy:
```powershell
# Python server
Get-Process python

# Cloudflared tunnel
Get-Process cloudflared
```

#### Zkontrolujte port 8001:
```powershell
netstat -ano | findstr :8001
```

### 7. 💡 Rychlé řešení

Nejjednodušší způsob - použijte lokální přístup:

1. Server běží na: `http://127.0.0.1:8001/files/`
2. Pokud potřebujete přístup zvenčí, použijte:
   - Lokální síť (HOST=0.0.0.0) - pouze v lokální síti
   - Nebo zkuste jiný tunnel (localtunnel, serveo, atd.)

## Doporučené řešení

**Pro rychlý test:**
1. Otevřete `http://127.0.0.1:8001/files/` lokálně
2. Pokud potřebujete přístup zvenčí, použijte Cloudflare Tunnel znovu

**Pro produkci:**
- Použijte vlastní server s veřejnou IP
- Nebo použijte správně nakonfigurovaný Cloudflare Tunnel s account

---

**Vytvořeno:** 2025-01-27

