# 🚀 Nasazení TooZ Hub 2 na hub.toozservis.cz

## 📋 Přehled architektury

```
bot.toozservis.cz  → chatbot (TooZ Autopilot) - JINÝ PROJEKT
hub.toozservis.cz  → TooZ Hub 2 backend (FastAPI) - NOVÝ
www.toozservis.cz  → Webnode (frontend s iframe)
```

Každá služba má vlastní subdoménu - čisté rozdělení, žádné konflikty.

---

## 1️⃣ Cloudflare DNS nastavení

### Varianta A: Cloudflare Tunnel (doporučeno)

**V Cloudflare Dashboard → DNS:**

1. Přidat nový CNAME záznam:
   ```
   Type: CNAME
   Name: hub
   Target: [váš-tunnel-hostname].cfargotunnel.com
   Proxy status: 🟡 Proxied (oranžový mrak)
   ```

2. V `cloudflared` konfiguraci přidat hostname:
   ```yaml
   tunnel: [tunnel-id]
   credentials-file: /path/to/credentials.json
   
   ingress:
     - hostname: hub.toozservis.cz
       service: http://127.0.0.1:8000
     - hostname: bot.toozservis.cz
       service: http://127.0.0.1:3000  # nebo port autopilota
     - service: http_status:404
   ```

3. Restartovat cloudflared:
   ```bash
   sudo systemctl restart cloudflared
   ```

### Varianta B: Přímé nasazení (A record)

**V Cloudflare Dashboard → DNS:**

1. Přidat nový A záznam:
   ```
   Type: A
   Name: hub
   IPv4 address: [veřejná IP serveru]
   Proxy status: 🟡 Proxied (oranžový mrak)
   ```

2. Na serveru nastavit HTTPS (Caddy/nginx + certbot):
   ```bash
   # Caddy příklad
   hub.toozservis.cz {
       reverse_proxy localhost:8000
   }
   ```

---

## 2️⃣ Konfigurace TooZ Hub 2

### Nastavení v `.env` souboru

Vytvořte nebo upravte `.env` soubor v kořenovém adresáři projektu:

```bash
# Environment
ENVIRONMENT=production

# Server
HOST=127.0.0.1
PORT=8000

# Veřejná API URL
PUBLIC_API_BASE_URL=https://hub.toozservis.cz

# CORS - povolené origins (Webnode + případně lokální dev)
ALLOWED_ORIGINS=https://www.toozservis.cz,https://toozservis.cz

# JWT Secret (VYTVOŘTE SILNÝ KLÍČ!)
JWT_SECRET_KEY=[vygenerujte-silny-nahodny-klic-pro-produkci]

# Databáze (pokud chcete použít jinou)
VEHICLE_DB_URL=sqlite:///./vehicles.db
```

### Generování JWT Secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 3️⃣ Úprava kódu (CORS)

CORS je již správně nakonfigurován v `src/core/config.py` a `src/server/main.py`.

Při `ENVIRONMENT=production` automaticky povolí:
- `https://www.toozservis.cz`
- `https://toozservis.cz`

Můžete přidat další přes proměnnou `ALLOWED_ORIGINS`.

---

## 4️⃣ Napojení na Webnode

### Varianta A: iframe (nejjednodušší)

V Webnode editoru na stránce typu "TOOZHUB APLIKACE" nebo "Můj vozový park":

```html
<iframe 
  src="https://hub.toozservis.cz/web/index.html" 
  style="width: 100%; height: 90vh; border: none; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
  allow="camera; microphone; geolocation">
</iframe>
```

**Nebo použijte iframe verzi (menší):**

Vložte do Webnode tento HTML:

```html
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TooZ Hub 2</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { height: 100%; overflow: hidden; }
        iframe { 
            width: 100%; 
            min-height: 100vh; 
            height: 100vh;
            border: none; 
            display: block; 
        }
    </style>
</head>
<body>
    <iframe 
        id="appFrame" 
        src="https://hub.toozservis.cz/web/index.html" 
        allow="camera; microphone; geolocation" 
        scrolling="auto">
    </iframe>
    <script>
        const iframe = document.getElementById('appFrame');
        iframe.addEventListener('load', () => {
            try {
                // Automaticky upravit výšku iframe podle obsahu
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                const height = Math.max(
                    iframeDoc.body.scrollHeight,
                    iframeDoc.body.offsetHeight,
                    iframeDoc.documentElement.clientHeight,
                    iframeDoc.documentElement.scrollHeight,
                    iframeDoc.documentElement.offsetHeight
                );
                iframe.style.height = height + 'px';
            } catch (e) {
                // Cross-origin - použít default výšku
                iframe.style.height = '100vh';
            }
        });
    </script>
</body>
</html>
```

### Varianta B: JS Widget (pokročilejší, pro budoucí rozšíření)

Pro tuto variantu by bylo potřeba vytvořit widget endpoint v TooZ Hub 2, což je mimo rozsah této dokumentace.

---

## 5️⃣ Aktualizace `web/index.html` pro produkci

V `web/index.html` (nebo `web/index_iframe.html`) je potřeba nastavit správnou API URL.

Zkontrolujte, že v JavaScriptu je:

```javascript
const DEFAULT_API_URL = 'https://hub.toozservis.cz';
```

Nebo ještě lépe - automatická detekce:

```javascript
// Automatická detekce API URL
const DEFAULT_API_URL = window.location.hostname === 'hub.toozservis.cz' 
    ? 'https://hub.toozservis.cz'
    : (window.location.origin || 'http://localhost:8000');
```

---

## 6️⃣ Postup nasazení

### Krok 1: Příprava na serveru

```bash
cd /home/toozservis/TOOZHUB2

# Aktualizovat z Gitu (pokud používáte Git)
git pull

# Aktivovat venv
source venv/bin/activate

# Aktualizovat závislosti
pip install -r requirements.txt

# Vytvořit/upravit .env soubor
nano .env
# (vložte konfiguraci z výše)
```

### Krok 2: Záloha databáze (pokud existuje)

```bash
cp vehicles.db vehicles.db.backup-$(date +%Y%m%d)
```

### Krok 3: Testování lokálně

```bash
# Spustit server lokálně pro test
ENVIRONMENT=production PUBLIC_API_BASE_URL=https://hub.toozservis.cz \
  python3 -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Krok 4: Nastavení systemd service (pokud ještě není)

Vytvořte `/etc/systemd/system/toozhub-server.service`:

```ini
[Unit]
Description=TooZ Hub 2 API Server
After=network.target

[Service]
Type=simple
User=toozservis
WorkingDirectory=/home/toozservis/TOOZHUB2
Environment="PATH=/home/toozservis/TOOZHUB2/venv/bin"
EnvironmentFile=/home/toozservis/TOOZHUB2/.env
ExecStart=/home/toozservis/TOOZHUB2/venv/bin/uvicorn src.server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktivace:

```bash
sudo systemctl daemon-reload
sudo systemctl enable toozhub-server
sudo systemctl start toozhub-server
sudo systemctl status toozhub-server
```

### Krok 5: DNS ověření

Počkejte 5-10 minut na propagaci DNS, pak otestujte:

```bash
curl -I https://hub.toozservis.cz/health
```

Mělo by vrátit `200 OK`.

### Krok 6: Vložení do Webnode

Postupujte podle sekce "4️⃣ Napojení na Webnode" výše.

---

## 7️⃣ Monitoring a logy

### Zobrazení logů

```bash
# Systemd service logy
sudo journalctl -u toozhub-server -f

# Posledních 50 řádků
sudo journalctl -u toozhub-server -n 50
```

### Health check

```bash
curl https://hub.toozservis.cz/health
```

Odpověď:
```json
{
  "status": "online",
  "service": "TooZ Hub 2 API",
  "version": "2.0.0"
}
```

---

## 8️⃣ Bezpečnost

### ✅ Co je potřeba udělat:

1. **JWT Secret** - Vytvořte silný náhodný klíč (viz výše)
2. **HTTPS** - Cloudflare Tunnel automaticky zajišťuje HTTPS
3. **CORS** - Je správně nastaveno pro produkci
4. **Databáza** - Zkontrolujte oprávnění souboru `vehicles.db` (např. 600)
5. **Environment variables** - `.env` soubor by měl mít oprávnění 600

```bash
chmod 600 .env
chmod 600 vehicles.db
```

### ⚠️ Důležité:

- **NEVKLÁDEJTE** `.env` do Gitu (je v `.gitignore`)
- **NEVKLÁDEJTE** JWT secret do Gitu
- Používejte silné heslo pro databázi (pokud použijete PostgreSQL)

---

## 9️⃣ Troubleshooting

### Server neběží

```bash
sudo systemctl status toozhub-server
sudo journalctl -u toozhub-server -n 50
```

### DNS nefunguje

Zkontrolujte v Cloudflare Dashboard, zda je záznam správný a aktivní.

### CORS chyby

Zkontrolujte, že `ALLOWED_ORIGINS` v `.env` obsahuje `https://www.toozservis.cz`.

### 502 Bad Gateway

- Zkontrolujte, zda server běží: `sudo systemctl status toozhub-server`
- Zkontrolujte cloudflared logy: `sudo journalctl -u cloudflared -n 50`
- Zkontrolujte, zda je port 8000 správně nastaven v cloudflared configu

---

## 🔟 Otestování po nasazení

1. **Health check:**
   ```bash
   curl https://hub.toozservis.cz/health
   ```

2. **Root endpoint:**
   ```bash
   curl https://hub.toozservis.cz/
   ```

3. **Web interface:**
   Otevřete v prohlížeči: `https://hub.toozservis.cz/web/index.html`

4. **Z Webnode:**
   Otevřete stránku s iframe v Webnode a zkontrolujte, že se aplikace načte.

---

## 📝 Shrnutí kroků

1. ✅ Vytvořit DNS záznam `hub` → CNAME na tunnel
2. ✅ Aktualizovat cloudflared config
3. ✅ Vytvořit/upravit `.env` soubor
4. ✅ Nastavit systemd service
5. ✅ Restartovat služby
6. ✅ Otestovat health check
7. ✅ Vložit iframe do Webnode

---

## 🎯 Výsledek

Po nasazení:

- **API:** `https://hub.toozservis.cz`
- **Web UI:** `https://hub.toozservis.cz/web/index.html`
- **Webnode:** iframe na `https://www.toozservis.cz/toozhub-aplikace`
- **Chatbot:** `https://bot.toozservis.cz` (nezávislý projekt)

Vše funguje nezávisle a čistě odděleno! 🚀



