# 🌐 Nastavení Cloudflare Tunnel pro TooZ Hub 2

## ✅ Co bylo provedeno

### 1. Konfigurace serveru
- ✅ Port změněn z 8001 na **8000**
- ✅ HOST změněn z 127.0.0.1 na **0.0.0.0** (pro Cloudflare Tunnel)
- ✅ CORS aktualizován pro doménu `hub.toozservis.cz`

### 2. Cloudflare Tunnel konfigurace
- ✅ Vytvořena složka `cloudflared/`
- ✅ Vytvořen soubor `cloudflared/config.yml` s konfigurací tunelu `tooz-hub2`

### 3. Spouštěcí skripty
- ✅ `start_server_production.bat` - Spuštění serveru na 0.0.0.0:8000
- ✅ `start_cloudflare_tunnel.bat` - Spuštění Cloudflare Tunnel
- ✅ `install_cloudflare_tunnel_service.ps1` - Instalace jako Windows služba

## 📋 Postup nastavení

### Krok 1: Vytvořit Cloudflare Tunnel

Pokud ještě nemáte vytvořený tunnel `tooz-hub2`:

```bash
cloudflared tunnel create tooz-hub2
```

Tento příkaz:
- Vytvoří tunnel s názvem `tooz-hub2`
- Uloží credentials do `C:\Users\djtoo\.cloudflared\tooz-hub2.json`
- Zobrazí UUID tunelu (bude potřeba pro DNS)

### Krok 2: Zkontrolovat credentials soubor

Ověřte, že soubor existuje:
```
C:\Users\djtoo\.cloudflared\tooz-hub2.json
```

Pokud neexistuje, vytvořte tunnel (Krok 1).

### Krok 3: Nastavit DNS záznam v Cloudflare

1. Přihlaste se do Cloudflare dashboardu
2. Vyberte doménu `toozservis.cz`
3. Přejděte na **DNS** → **Records**
4. Vytvořte nový CNAME záznam:
   - **Type**: CNAME
   - **Name**: `hub`
   - **Target**: `<UUID>.cfargotunnel.com` (UUID získáte z `tooz-hub2.json` nebo z výstupu `cloudflared tunnel create`)
   - **Proxy status**: ✅ **Proxied** (oranžový mrak)
   - **TTL**: Auto

**Příklad:**
```
Type: CNAME
Name: hub
Target: a1b2c3d4-e5f6-7890-abcd-ef1234567890.cfargotunnel.com
Proxy: Proxied (ON)
```

### Krok 4: Spustit server

```bash
# Možnost 1: Použít batch skript
start_server_production.bat

# Možnost 2: Přímo
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

Server by měl běžet na `http://0.0.0.0:8000` (nebo `http://localhost:8000`).

### Krok 5: Spustit Cloudflare Tunnel

```bash
# Možnost 1: Použít batch skript
start_cloudflare_tunnel.bat

# Možnost 2: Přímo
cloudflared tunnel run tooz-hub2
```

Tunnel se připojí k Cloudflare a začne směrovat provoz z `hub.toozservis.cz` na `localhost:8000`.

### Krok 6: Otestovat dostupnost

Počkejte 1-2 minuty na propagaci DNS, pak otestujte:

```bash
# Health check
curl https://hub.toozservis.cz/health

# Nebo otevřete v prohlížeči
https://hub.toozservis.cz/health
```

Měli byste vidět JSON odpověď:
```json
{
  "status": "online",
  "service": "TooZ Hub 2 API",
  "version": "2.0.0"
}
```

## 🔧 Automatické spouštění (Windows služba)

### Instalace služby

```powershell
# Spustit jako Administrator
.\install_cloudflare_tunnel_service.ps1
```

Skript:
1. Zkontroluje, zda je NSSM nainstalován
2. Zkontroluje, zda je cloudflared v PATH
3. Nainstaluje Cloudflare Tunnel jako Windows službu
4. Nastaví automatické spuštění při startu systému

### Správa služby

```powershell
# Spustit službu
Start-Service cloudflared

# Zastavit službu
Stop-Service cloudflared

# Zobrazit status
Get-Service cloudflared

# Zobrazit logy
Get-EventLog -LogName Application -Source cloudflared -Newest 10
```

### Odstranění služby

```powershell
# Jako Administrator
C:\Program Files\nssm\nssm.exe remove cloudflared confirm
```

## 🔍 Řešení problémů

### Problém: "Tunnel not found"

**Řešení:**
```bash
# Zkontrolovat, zda tunnel existuje
cloudflared tunnel list

# Pokud neexistuje, vytvořit
cloudflared tunnel create tooz-hub2
```

### Problém: "Credentials file not found"

**Řešení:**
- Ověřte cestu v `cloudflared/config.yml`
- Výchozí cesta: `C:\Users\djtoo\.cloudflared\tooz-hub2.json`
- Pokud je jiná, upravte `credentials-file` v `config.yml`

### Problém: "Connection refused" nebo "502 Bad Gateway"

**Řešení:**
1. Zkontrolujte, zda server běží na portu 8000:
   ```bash
   curl http://localhost:8000/health
   ```

2. Zkontrolujte, zda tunnel běží:
   ```bash
   cloudflared tunnel run tooz-hub2 --loglevel debug
   ```

3. Zkontrolujte firewall - port 8000 musí být přístupný lokálně

### Problém: CORS chyby

**Řešení:**
- Ověřte, že `hub.toozservis.cz` je v `ALLOWED_ORIGINS`
- Zkontrolujte `src/core/config.py` a `src/server/config.py`
- Restartujte server po změně konfigurace

### Problém: DNS nepropaguje

**Řešení:**
- Počkejte 5-10 minut na propagaci DNS
- Zkontrolujte DNS záznam v Cloudflare dashboardu
- Ověřte, že CNAME má **Proxied** status (oranžový mrak)

## 📝 Konfigurační soubory

### `cloudflared/config.yml`
```yaml
tunnel: tooz-hub2
credentials-file: C:\Users\djtoo\.cloudflared\tooz-hub2.json

ingress:
  - hostname: hub.toozservis.cz
    service: http://localhost:8000
  - service: http_status:404
```

### `.env` (volitelné)
```env
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=production
ALLOWED_ORIGINS=https://toozservis.cz,https://www.toozservis.cz,https://hub.toozservis.cz
```

## ✅ Ověření nastavení

### Checklist:

- [ ] Tunnel `tooz-hub2` vytvořen
- [ ] Credentials soubor existuje na správné cestě
- [ ] DNS CNAME záznam vytvořen v Cloudflare
- [ ] DNS záznam má **Proxied** status
- [ ] Server běží na `0.0.0.0:8000`
- [ ] Cloudflare Tunnel běží
- [ ] `https://hub.toozservis.cz/health` vrací 200 OK
- [ ] CORS je správně nakonfigurován

## 🔗 Užitečné odkazy

- [Cloudflare Tunnel dokumentace](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [Cloudflare Tunnel CLI reference](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/)
- [NSSM dokumentace](https://nssm.cc/usage)

---

**Vytvořeno:** 2025-01-27  
**Projekt:** TooZ Hub 2  
**Doména:** hub.toozservis.cz

