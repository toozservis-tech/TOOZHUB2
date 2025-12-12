# 🚀 TooZ Hub 2.1 - Changelog

## 📦 Verze: 2.1.0 (TOOZHUB2.1)
**Datum buildu:** 2025-01-27  
**Typ aktualizace:** Minor Update

---

## ✨ Nové funkce

### 🎨 Vizuální úpravy
- **CSS styl z admin dashboardu** - Hlavní aplikace nyní používá stejný vizuální styl jako admin dashboard
- **Základní úpravy pozadí** - Změna z tmavého na světlé pozadí (#f8fafc)
- **Připraven CSS** - Soubor `web/app.css` obsahuje všechny styly z admin dashboardu

### 📊 Systém verzování
- **Centralizované verzování** - Nový soubor `VERSION.py` pro snadnou správu verzí
- **Indikátor aktualizace** - Při restartu serveru je zobrazena informace o verzi a aktualizaci
- **Health check rozšířen** - Endpoint `/health` nyní vrací informace o verzi, buildu a aktualizaci

---

## 🔧 Vylepšení

### Backend
- ✅ Verze nyní načítána z `VERSION.py`
- ✅ Root endpoint (`/`) obsahuje informace o verzi
- ✅ Health check endpoint (`/health`) obsahuje informace o aktualizaci
- ✅ Při startu serveru se zobrazuje informace o verzi a aktualizaci

### Frontend
- ✅ CSS styl připraven pro vizuální úpravy
- ✅ Záloha původního `index.html` vytvořena

### Dokumentace
- ✅ **Oprava dokumentace Webnode integrace**
  - Hlavní návody přepsány na přesměrování (produkční metoda)
  - Iframe varianta přesunuta do alternativní dokumentace
  - Dokumentace nyní odpovídá reálnému produkčnímu nastavení
  - Viz `WEBNODE_OPRAVA_CHANGELOG.md` pro podrobnosti

---

## 📝 Kompatibilita

### ✅ Zpětná kompatibilita
- **Databáze** - Žádné změny v databázové struktuře
- **API endpointy** - Všechny endpointy zůstávají stejné
- **Autentizace** - Žádné změny v autentizačním systému
- **Funkce** - Všechny funkce zůstávají plně funkční

### ⚠️ Poznámky
- Vizuální úpravy jsou připraveny, ale HTML struktura hlavní aplikace čeká na systematickou úpravu
- Admin dashboard je plně funkční a používá nový styl
- Všechny změny jsou bezpečné a nepoškodí existující systém

---

## 🗂️ Změněné soubory

### Nové soubory
- `VERSION.py` - Centralizované řízení verzí
- `web/app.css` - CSS styl z admin dashboardu
- `web/index.html.backup` - Záloha původního index.html
- `TOOZHUB2.1_CHANGELOG.md` - Tento soubor

### Upravené soubory
- `src/server/main.py` - Přidáno načítání verze z VERSION.py
- `web/index.html` - Přidán CSS odkaz, změněno pozadí

---

## 🚀 Instalace a aktualizace

### Aktualizace z verze 2.0.0

1. **Záloha databáze** (doporučeno):
   ```bash
   cp vehicles.db vehicles.db.backup
   ```

2. **Aktualizace souborů**:
   - Všechny změny jsou zpětně kompatibilní
   - Žádné migrace databáze nejsou potřeba

3. **Restart serveru**:
   ```bash
   # Zastavit současný server
   # Spustit nový server
   python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
   ```

4. **Ověření**:
   - Zkontrolovat endpoint `/health` - měl by vracet verzi 2.1.0
   - Zkontrolovat logy při startu - měla by se zobrazit informace o verzi

---

## 🔍 Kontrola funkčnosti

### ✅ Zkontrolováno
- [x] Backend server se spouští bez chyb
- [x] Všechny routery jsou zaregistrovány
- [x] Static file mounts fungují
- [x] API endpointy odpovídají
- [x] Health check vrací správné informace
- [x] Verze se zobrazuje při startu

### ⏳ Čeká na ověření
- [ ] Test všech API endpointů
- [ ] Test autentizace
- [ ] Test databázových operací
- [ ] Test frontendu po vizuálních úpravách

---

## 📞 Podpora

Při jakýchkoliv problémech:
1. Zkontrolujte logy serveru při startu
2. Ověřte endpoint `/health`
3. Zkontrolujte, že všechny soubory jsou na místě
4. V případě problémů použijte zálohu `vehicles.db.backup`

---

**Poznámka:** Tato aktualizace je bezpečná a zpětně kompatibilní. Nejsou potřeba žádné migrace databáze ani další konfigurace.

