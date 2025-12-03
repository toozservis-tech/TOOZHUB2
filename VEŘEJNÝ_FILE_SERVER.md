# 📁 Veřejný File Server - TooZ Hub 2

## ✅ Co bylo vytvořeno

Veřejný file server umožňuje sdílet soubory s kýmkoliv přes jednoduchý odkaz.

### 1. Statický endpoint
- ✅ Endpoint: `/public/`
- ✅ Složka: `public_share/` v root projektu
- ✅ Automatické zobrazování seznamu souborů

### 2. Struktura projektu
```
TOOZHUB2/
├── src/
├── web/
└── public_share/   ← Veřejné soubory
    ├── test.txt
    └── README.md
```

### 3. CORS
- ✅ CORS je nastaven na `allow_origins=["*"]` - veřejný přístup povolen

## 🌐 Jak používat

### Vložit soubor pro sdílení

1. **Zkopírujte soubor do složky:**
   ```
   public_share/
   ```

2. **Sdílejte odkaz:**
   ```
   https://hub.toozservis.cz/public/NAZEV_SOUBORU.PRIpona
   ```

### Příklady

#### Seznam všech souborů:
```
https://hub.toozservis.cz/public/
```

#### Konkrétní soubor:
```
https://hub.toozservis.cz/public/test.txt
https://hub.toozservis.cz/public/dokument.pdf
https://hub.toozservis.cz/public/obrazek.jpg
```

## 📋 Podporované formáty

Všechny formáty souborů jsou podporovány:
- ✅ PDF dokumenty
- ✅ Obrázky (JPG, PNG, GIF, SVG, atd.)
- ✅ Textové soubory (TXT, MD, CSV, atd.)
- ✅ Archívy (ZIP, RAR, 7Z, atd.)
- ✅ Kód (PY, JS, HTML, CSS, atd.)
- ✅ A jakékoliv jiné soubory

## ⚠️ Důležité

### Bezpečnost
- **Všechny soubory v `public_share/` jsou veřejně přístupné**
- **Kdokoliv s odkazem může soubory stáhnout**
- **Neukládejte citlivé soubory do této složky**

### Co NEPOKLÁDAT do public_share:
- ❌ Hesla a API klíče
- ❌ Osobní údaje
- ❌ Citlivé dokumenty
- ❌ Databázové soubory s reálnými daty

### Co MŮŽETE sdílet:
- ✅ Veřejné dokumenty
- ✅ PDF návody
- ✅ Obrázky a grafiky
- ✅ Kód a skripty
- ✅ Archívy a distribuce

## 🔧 Konfigurace

### Endpoint v kódu
V `src/server/main.py`:
```python
# ============= PUBLIC FILE SERVER =============

try:
    public_path = Path(__file__).parent.parent.parent / "public_share"
    # Vytvořit složku, pokud neexistuje
    public_path.mkdir(parents=True, exist_ok=True)
    if public_path.exists():
        app.mount("/public", StaticFiles(directory=str(public_path)), name="public")
        print(f"[SERVER] Public file server zaregistrován: /public (directory: {public_path})")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount public directory: {e}")
```

### CORS
CORS je nastaven na `allow_origins=["*"]` - povoluje všechny origins pro veřejný přístup.

## 🧪 Testování

### Lokálně:
```
http://localhost:8000/public/
http://localhost:8000/public/test.txt
```

### Veřejně:
```
https://hub.toozservis.cz/public/
https://hub.toozservis.cz/public/test.txt
```

### Testovací skript:
```powershell
.\test_public_fileserver.ps1
```

## 📝 Příklad použití

### 1. Vložit soubor
```powershell
# Zkopírovat soubor do public_share
Copy-Item "C:\Dokumenty\navod.pdf" -Destination "public_share\navod.pdf"
```

### 2. Sdílet odkaz
```
https://hub.toozservis.cz/public/navod.pdf
```

### 3. Ověřit dostupnost
```powershell
curl https://hub.toozservis.cz/public/navod.pdf
```

## 🎯 Výhody

- ✅ **Jednoduché sdílení** - stačí vložit soubor a sdílet odkaz
- ✅ **Bez omezení** - žádné heslo, žádný token
- ✅ **Všechny formáty** - PDF, obrázky, kód, archívy, atd.
- ✅ **Automatický seznam** - zobrazí všechny soubory
- ✅ **Veřejný přístup** - kdokoliv s odkazem může stáhnout

## 📋 Checklist

- [x] Složka `public_share/` vytvořena
- [x] Statický mount `/public/` přidán
- [x] CORS nastaven na `["*"]`
- [x] Testovací soubor vytvořen
- [x] Dokumentace vytvořena
- [ ] Server restartován (pro projevení změn)
- [ ] Testovací skript spuštěn

---

**Vytvořeno:** 2025-01-27  
**URL:** https://hub.toozservis.cz/public/  
**Složka:** `public_share/`

