# Nastavení MDČR API klíče

## Konfigurace API klíče

Pro správné fungování VIN dekodéru je nutné nastavit API klíč pro MDČR API (dataovozidlech.cz).

### 1. Přidání do .env souboru

V kořenovém adresáři projektu vytvořte nebo upravte soubor `.env` a přidejte:

```env
# MDČR API Configuration
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
```

### 2. Ověření nastavení

Po přidání API klíče restartujte backend server, aby se načetly nové proměnné prostředí.

### 3. Testování

Otevřete Swagger dokumentaci na `/docs` a otestujte endpoint:
- `POST /api/vehicles/decode-vin`
- Body: `{"vin": "TMBJF73T2B9044629"}`

Měla by se vrátit odpověď s daty o vozidle.

### 4. Logy

V backend logách byste měli vidět:
```
[MDČR] ✅ API odpověď přijata
[MDČR] ✅ Úspěšně dekódováno: Škoda Auto Superb (2011)
```

Pokud vidíte:
```
[MDČR] API není nakonfigurováno (BASE_URL nebo TOKEN chybí)
```
znamená to, že API klíč není správně nastaven.

