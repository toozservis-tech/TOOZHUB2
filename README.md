# 🚗 Správa vozidel

Komplexní desktop a web aplikace pro správu vozidel, dokumentů a dalších nástrojů.

## ✨ Funkce

### Vehicle Hub
- 🚗 Správa vozidel s databází
- 🔍 VIN dekodér s integrací MDČR a NHTSA API
- 📊 Přehled o vozidle (značka, model, rok, motor, pneumatiky)
- 📝 Servisní záznamy

### Email Client
- 📧 Odesílání emailů s přílohami
- 📨 HTML šablony pro připomínky
- ⚙️ Konfigurovatelné SMTP nastavení

### PDF Nástroje
- 📄 Sloučení více PDF souborů
- ✂️ Rozdělení PDF na jednotlivé stránky
- 🔄 Rotace stránek
- 📝 Vytvoření PDF z textu

### Image Tools
- 🖼️ Změna velikosti obrázků
- ✂️ Ořez a rotace
- 🎨 Filtry (rozmazání, zostření, kontury, šedá)
- 💡 Úprava jasu
- 🔄 Konverze formátů (PNG, JPEG, BMP, GIF, WEBP)

### Hlasové ovládání (experimentální)
- 🎤 Rozpoznávání řeči (vyžaduje SpeechRecognition)
- 🔊 Text-to-speech (vyžaduje pyttsx3)

## 🛠️ Instalace

### 1. Klonování repozitáře
```bash
git clone https://github.com/<váš-účet>/<název-repozitáře>.git
cd <název-adresáře>
```

Aktuální produkční klon může stále používat historický název repozitáře na GitHubu – viz `TECHNICAL_RENAME_BACKLOG.md`.

### 2. Vytvoření virtuálního prostředí

**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalace závislostí

**Windows:**
```powershell
pip install -r requirements.txt
```

**Linux/Mac:**
```bash
pip install -r requirements.txt
```

### 4. Konfigurace (volitelné)
Vytvořte soubor `.env` v kořenovém adresáři:
```env
# Server
HOST=127.0.0.1
PORT=8000
ENVIRONMENT=development

# JWT
JWT_SECRET_KEY=your-secret-key-change-this

# Email (volitelné)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

## 🚀 Spuštění

### Spuštění projektu přes Cloudflare Tunnel (Windows)

#### 1. Instalace cloudflared

Stáhněte a nainstalujte `cloudflared` z oficiální dokumentace:
- **Odkaz:** https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

Nebo použijte winget:
```powershell
winget install --id Cloudflare.cloudflared
```

#### 2. Přihlášení do Cloudflare

```powershell
cloudflared tunnel login
```

#### 3. Vytvoření tunelu pro tento projekt

```powershell
cloudflared tunnel create tooz-hub2
```

#### 4. Přidání DNS záznamu

```powershell
cloudflared tunnel route dns tooz-hub2 hub.toozservis.cz
```

**Konfigurace projektu:**
- **Název tunelu:** `tooz-hub2`
- **Hostname:** `hub.toozservis.cz`
- **Port serveru:** `8000`

#### 5. Spuštění serveru + tunelu najednou

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start_all.ps1
```

Nebo spusťte jednotlivě:
```powershell
# Spustit pouze server
powershell -ExecutionPolicy Bypass -File .\scripts\windows\run_server.ps1

# Spustit pouze tunnel
powershell -ExecutionPolicy Bypass -File .\scripts\windows\run_tunnel.ps1
```

#### 6. Autostart při spuštění Windows

1. Stiskněte `Win + R`
2. Zadejte: `shell:startup`
3. Vytvořte zástupce (shortcut) na soubor `scripts\windows\start_all.ps1`
4. Pravým tlačítkem na zástupce → Vlastnosti
5. Do pole "Cíl" zadejte:
   ```
   powershell.exe -ExecutionPolicy Bypass -File "C:\Projects\sprava-vozidel\scripts\windows\start_all.ps1"
   ```
6. (Volitelně) Nastavte "Spustit" na "Minimalizováno"

Server a tunnel se nyní spustí automaticky při každém přihlášení do Windows.

### Tray ikonka (Windows) – stav serveru a autostart

Tray aplikace zobrazuje stav serveru v systémové liště a umožňuje rychlý restart serveru nebo tunelu.

#### Instalace závislostí

```powershell
pip install -r requirements.txt
```

Požadované balíčky: `pystray`, `Pillow`, `requests` (již jsou v `requirements.txt`)

#### Spuštění tray aplikace

**Manuálně:**
```powershell
python tray\tray_manager.py
```

**Nebo pomocí PowerShell skriptu (spustí se na pozadí bez viditelného okna):**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start_tray.ps1
```

Tray aplikace se spustí na pozadí bez viditelného PowerShell okna. Ikona se zobrazí v systémové liště (u hodin).

#### Autostart tray aplikace

Pro automatické spuštění tray aplikace při každém přihlášení do Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\add_tray_to_startup.ps1
```

Tento skript automaticky vytvoří zástupce v Windows Startup složce s názvem `SpravaVozidel_tray.lnk`.

**Poznámka:** Při startu Windows se tray aplikace spustí automaticky na pozadí bez viditelného okna. Zobrazí se pouze ikona v systémové liště.

**Ruční odebrání z Autostartu:**
1. Stiskněte `Win + R`
2. Zadejte: `shell:startup`
3. Odstraňte soubor `SpravaVozidel_tray.lnk`

#### Funkce tray ikonky

**Ikony:**
- 🟢 **Zelená** = Server běží a odpovídá na health check (`/health`)
- 🔴 **Červená** = Server nedostupný nebo neodpovídá

**Menu (pravý klik na ikonu):**
- **Otevřít aplikaci** → Otevře `https://hub.toozservis.cz` v prohlížeči
- **Restart serveru** → Restartuje FastAPI server pomocí `scripts/windows/run_server.ps1`
- **Restart tunelu** → Restartuje Cloudflare Tunnel pomocí `scripts/windows/run_tunnel.ps1`
- **Ukončit** → Ukončí tray aplikaci

**Poznámky:**
- Tray aplikace běží na pozadí a nevyžaduje otevřený terminál
- Health check se provádí každé 3 sekundy
- Ikona se automaticky aktualizuje podle stavu serveru

### Backend server (ruční spuštění)

**Windows:**
```powershell
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

**Linux/Mac:**
```bash
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

Server běží na `http://127.0.0.1:8000`

## Runtime DB pravda

- Backend source-of-truth je `DATABASE_URL` v [`src/core/config.py`](/opt/toozhub2/app/src/core/config.py).
- Pokud není nastavené ENV, výchozí runtime SQLite je `../data/vehicles.db`, tj. na tomto serveru `/opt/toozhub2/data/vehicles.db`.
- `VEHICLE_DB_URL` je pouze legacy compat alias.
- `app/data/vehicles.db` může na serveru stále existovat jako starý snapshot / symlink target. Není to produkční pravda, pokud runtime ukazuje na `/opt/toozhub2/data/vehicles.db`.

### Desktop aplikace

**Windows/Linux/Mac:**
```powershell
python src/app/main.py
```

### Web interface
Otevřete v prohlížeči: `http://127.0.0.1:8000/web/index.html`

## 📁 Struktura projektu

```
sprava-vozidel/
├── src/
│   ├── app/
│   │   └── main.py          # Desktop aplikace (PySide6)
│   ├── core/
│   │   ├── config.py        # Konfigurace
│   │   └── security.py      # Bezpečnost (bcrypt, JWT)
│   ├── modules/
│   │   ├── auth/            # Autentizace
│   │   ├── vehicle_hub/     # Správa vozidel
│   │   ├── email_client/    # Email
│   │   ├── pdf_manager/     # PDF nástroje
│   │   ├── image_tools/     # Obrázky
│   │   └── voice/           # Hlasové ovládání
│   └── server/
│       └── main.py          # FastAPI backend
├── web/
│   └── index.html           # Web interface
├── data/                    # Uložené soubory
├── requirements.txt
└── README.md
```

## 🔐 Bezpečnost

- **Hesla**: Hashována pomocí bcrypt (s fallbackem na SHA256)
- **Autentizace**: JWT tokeny s konfigurovatelnou expirací
- **CORS**: Konfigurovatelné origins

## 🔧 API Endpointy

| Endpoint | Metoda | Popis |
|----------|--------|-------|
| `/user/register` | POST | Registrace uživatele |
| `/user/login` | POST | Přihlášení (vrací JWT token) |
| `/user/me` | GET | Info o přihlášeném uživateli |
| `/user/ares` | GET | Načtení dat z ARES |
| `/vehicles` | GET/POST | Seznam/přidání vozidel |
| `/vehicles/{id}` | GET/DELETE | Detail/smazání vozidla |
| `/vehicles/decode-vin` | POST | Dekódování VIN |
| `/health` | GET | Health check |

## 📋 Požadavky

- Python 3.10+
- PySide6 (desktop app)
- FastAPI + Uvicorn (backend)
- SQLAlchemy (databáze)
- Selenium + Chrome (VIN dekodér)

### Volitelné závislosti
- PyPDF2, ReportLab (PDF nástroje)
- Pillow (obrázky)
- SpeechRecognition, pyttsx3 (hlas)

## 🔐 Registrace instalace (instance) přes API

Správa vozidel podporuje multi-tenant architekturu, kde každá instalace aplikace (instance) je registrována pod licenčním klíčem (tenant).

### Registrace nové instance

Desktopová aplikace nebo klient se registruje pomocí endpointu `/api/instances/register`:

**Request:**
```json
POST /api/instances/register
{
  "license_key": "VAS-LICENCNI-KLIC",
  "device_info": {
    "hostname": "PC-NAME",
    "os": "Windows 10",
    "app_version": "2.2.0"
  }
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "tenant_id": 1,
  "instance_id": 1
}
```

**Poznámky:**
- Pokud tenant s daným `license_key` neexistuje, vytvoří se automaticky nový tenant
- `access_token` je JWT token obsahující `tenant_id` a `instance_id`
- Token je potřeba ukládat lokálně (např. v konfiguračním souboru nebo databázi)

### Ping endpoint

Pro aktualizaci `last_seen_at` volá aplikace pravidelně `/api/instances/ping`:

**Request:**
```json
POST /api/instances/ping
Authorization: Bearer <access_token>
{
  "app_version": "2.2.0"
}
```

**Response:**
```json
{
  "status": "ok"
}
```

**Doporučení:**
- Volat při startu aplikace
- Volat každých 5-10 minut, pokud aplikace běží
- Aktualizovat `app_version`, pokud se změní verze aplikace

### Ukládání tokenu

Token by měl být uložen bezpečně na lokálním počítači:
- V konfiguračním souboru (např. `.env` nebo `config.json`)
- V lokální databázi (např. SQLite)
- V systémovém úložišti (Windows Registry, macOS Keychain, Linux Secret Service)

**Příklad ukládání:**
```python
# Při registraci
response = requests.post("https://hub.toozservis.cz/api/instances/register", json=payload)
data = response.json()
access_token = data["access_token"]

# Uložit token
with open("config.json", "w") as f:
    json.dump({"access_token": access_token}, f)
```

**Příklad použití tokenu:**
```python
# Při každém API volání
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get("https://hub.toozservis.cz/api/v1/vehicles", headers=headers)
```

## 🧪 CI / QA

### GitHub Actions

Projekt používá GitHub Actions pro automatické spouštění testů při každém push a pull requestu.

**Workflow:** `.github/workflows/qa.yml`

**Spuštění:**
- Automaticky při každém push a pull requestu
- Ručně přes GitHub Actions UI (workflow_dispatch)

**Kroky workflow:**
1. Setup Python 3.12 a instalace závislostí
2. Setup Node.js 20 a instalace Playwright závislostí
3. Spuštění backend serveru na pozadí
4. Spuštění API testů (pytest)
5. Spuštění E2E testů (Playwright)
6. Upload artefaktů (test reporty, screenshoty, videa)

**Artefakty:**
- Najdete v GitHub Actions UI → konkrétní run → "Artifacts"
- Obsahuje:
  - `pytest-report.xml` - JUnit XML report z API testů
  - `playwright-report/` - HTML report z E2E testů
  - Screenshoty a videa z failed testů

**Lokální spuštění:**

```powershell
# Spustit všechny testy (backend + API + E2E)
.\scripts\qa_run.ps1

# Pouze API testy
.\scripts\qa_run.ps1 -SkipBackend -SkipE2E

# Pouze E2E testy
.\scripts\qa_run.ps1 -SkipBackend -SkipAPI
```

Více informací v [QA_REPORT.md](QA_REPORT.md) a [tests/README.md](tests/README.md).

### Production Smoke Tests

Projekt obsahuje také **Production Smoke Tests** - read-only testy, které běží proti produkčnímu prostředí.

**Workflow:** `.github/workflows/prod-smoke.yml`

**Spuštění:**
- Automaticky 1× denně v 03:30 (Europe/Prague)
- Automaticky při push na `main` branch
- Ručně přes GitHub Actions UI (workflow_dispatch)

**GitHub Secrets (povinné):**
Pro spuštění production smoke testů musíš nastavit v GitHub Settings → Secrets and variables → Actions:
- `PROD_E2E_EMAIL` - Email pro přihlášení do produkce
- `PROD_E2E_PASSWORD` - Heslo pro přihlášení do produkce

**Co testují:**
- ✅ Načtení a přihlášení do aplikace
- ✅ Navigace mezi sekcemi (read-only)
- ✅ Ověření, že UI funguje bez chyb
- ❌ **Nevytvářejí, neupravují ani nemazají data**

**Artefakty:**
- Najdete v GitHub Actions UI → "Production Smoke Tests" workflow → "Artifacts"
- Retention: 30 dní

**Jak poznat problém:**
- ❌ **Červený křížek** v GitHub Actions = workflow selhal
- 📧 **Email notifikace** (pokud máš zapnuté v GitHub Settings → Notifications)
- 📊 **Artefakty** obsahují screenshoty a logy z failed testů

**⚠️ Důležité:** Workflow **NEOpravuje problémy automaticky** - pouze je detekuje. Když selže, musíš problém opravit ručně a pushnout opravu.

### 🤖 Automatická oprava workflow chyb

Projekt obsahuje **automatický systém pro detekci a opravu workflow chyb**:

**Workflow:** `.github/workflows/auto-fix.yml`

**Co dělá:**
- ✅ Automaticky analyzuje failed workflow runy
- ✅ Identifikuje typ chyby
- ✅ Pokusí se automaticky opravit (pokud je to možné)
- ✅ Vytvoří Pull Request s opravami
- ✅ Nebo vytvoří Issue, pokud oprava vyžaduje manuální zásah

**Spuštění:**
- Automaticky po každém failed workflow runu
- Automaticky každých 30 minut (scheduled check)
- Ručně přes GitHub Actions UI (workflow_dispatch)

**Lokální monitoring:**
```powershell
# Jednorázová kontrola
.\scripts\auto_fix_workflows.ps1 -RunOnce

# Kontinuální monitoring (kontrola každých 5 minut)
.\scripts\auto_fix_workflows.ps1 -CheckInterval 300
```

Více informací v [docs/AUTO_FIX_GUIDE.md](docs/AUTO_FIX_GUIDE.md).

Více informací v [CI_IMPLEMENTATION.md](CI_IMPLEMENTATION.md) a [docs/WORKFLOW_TROUBLESHOOTING.md](docs/WORKFLOW_TROUBLESHOOTING.md).

## 📄 Licence

MIT License

## 🤝 Přispívání

1. Fork repozitáře
2. Vytvořte feature branch (`git checkout -b feature/nova-funkce`)
3. Commit změn (`git commit -am 'Přidána nová funkce'`)
4. Push do branch (`git push origin feature/nova-funkce`)
5. Vytvořte Pull Request
