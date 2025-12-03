# 🚗 TooZ Hub 2

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
git clone https://github.com/your-repo/TOOZHUB2.git
cd TOOZHUB2
```

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

### Backend server

**Windows:**
```powershell
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

**Linux/Mac:**
```bash
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

Server běží na `http://127.0.0.1:8000`

### Desktop aplikace

**Windows/Linux/Mac:**
```powershell
python src/app/main.py
```

### Web interface
Otevřete v prohlížeči: `http://127.0.0.1:8000/web/index.html`

### Tray aplikace (Windows)

```powershell
python toozhub_tray_final.py
```

Nebo dvojklik na `start_toozhub_tray.bat`

## 📁 Struktura projektu

```
TOOZHUB2/
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

## 📄 Licence

MIT License

## 🤝 Přispívání

1. Fork repozitáře
2. Vytvořte feature branch (`git checkout -b feature/nova-funkce`)
3. Commit změn (`git commit -am 'Přidána nová funkce'`)
4. Push do branch (`git push origin feature/nova-funkce`)
5. Vytvořte Pull Request
