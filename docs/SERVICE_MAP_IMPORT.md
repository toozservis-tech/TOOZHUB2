# Servisní mapa – import dat (staging / produkční příprava)

Vlastní katalog servisních míst v tabulce `service_locations`.

**Tvrdé pravidlo:** Google Maps, Mapy.com, SerpAPI ani jiné komerční mapy **nejsou zdrojem katalogu servisů**. Slouží pouze jako navigace nebo volitelný tile podklad mapy. Katalog se buduje z **OpenStreetMap (Overpass)** a oficiálních zdrojů (MDČR STK/SME).

## Požadavky

- Migrace `20260520_0043` aplikovaná (`alembic upgrade head`)
- Python venv projektu
- Staging DB: `/opt/toozhub2-staging/data/vehicles_staging.db`
- Pro celou ČR doporučen **import po krajích**, ne jeden obří Overpass dotaz

## Doporučené pořadí importu

1. **Vždy nejdřív** `svitavy_test` (malá testovací oblast)
2. Potom **Pardubický kraj** (`pardubicky`)
3. Teprve potom **celá ČR** (`--all-regions`)

Endpoint `https://overpass-api.de/api/interpreter` může vracet HTTP 406. Doporučené mirror:

- `https://overpass.kumi.systems/api/interpreter` (může být z tohoto serveru nedostupný – timeout)
- `https://lz4.overpass-api.de/api/interpreter` (funkční alternativa)
- `https://overpass.openstreetmap.fr/api/interpreter`

Volitelně v `.env`: `OVERPASS_API_URL=https://lz4.overpass-api.de/api/interpreter`

---

## A) Test Overpass mirroru

```bash
cd /opt/toozhub2-staging/app

/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --test-overpass \
  --overpass-url https://overpass.kumi.systems/api/interpreter
```

Očekávaný výstup: `test-overpass PASS` s validním JSON (bez zápisu do DB).

---

## B) Stažení Svitavy bez zápisu do DB

```bash
/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --region svitavy_test \
  --fetch-overpass \
  --overpass-url https://overpass.kumi.systems/api/interpreter \
  --download-only \
  --save-json /tmp/osm_import \
  --query-debug
```

Soubor se uloží jako `/tmp/osm_import/svitavy_test_YYYYMMDD_HHMMSS.json`.

---

## C) Dry-run Svitavy

```bash
/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --region svitavy_test \
  --fetch-overpass \
  --overpass-url https://overpass.kumi.systems/api/interpreter \
  --dry-run
```

---

## D) Reálný import Svitavy ze souboru

```bash
/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --file /tmp/osm_import/<soubor_svitavy>.json \
  --batch-id osm-svitavy-001
```

---

## E) Reálný import Pardubický kraj

Pro velký kraj lze přidat `--split-bbox` (2×2 dlaždice):

```bash
/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --region pardubicky \
  --fetch-overpass \
  --overpass-url https://overpass.kumi.systems/api/interpreter \
  --save-json /tmp/osm_import \
  --sleep 8
```

---

## F) Import celé ČR po krajích

```bash
/opt/toozhub2/.venv/bin/python scripts/import_service_map_osm_cz.py \
  --all-regions \
  --fetch-overpass \
  --overpass-url https://overpass.kumi.systems/api/interpreter \
  --save-json /tmp/osm_import \
  --sleep 8
```

---

## G) DB kontrola počtů

```bash
sqlite3 /opt/toozhub2-staging/data/vehicles_staging.db "
SELECT category, source_type, verification_status, COUNT(*)
FROM service_locations
GROUP BY category, source_type, verification_status
ORDER BY category, source_type;
"
```

---

## H) Kontrola vadných bodů

```bash
sqlite3 /opt/toozhub2-staging/data/vehicles_staging.db "
SELECT id, name, category, city, lat, lng, source_type
FROM service_locations
WHERE lat IS NULL OR lng IS NULL OR name IS NULL OR name = ''
LIMIT 50;
"
```

---

## I) Restart stagingu

```bash
systemctl restart toozhub2-staging.service
```

---

## J) UI kontrola

1. Otevřít https://staging.hub.toozservis.cz
2. Ctrl+F5 (hard refresh)
3. Uživatel → Servisy
4. Filtr Autoservis / Pneuservis / STK
5. Posun mapy (bounds loading)
6. Klik na marker → detail bottom sheet
7. Navigace Mapy.cz (pouze navigace, ne zdroj katalogu)

---

## CLI reference (import skript)

| Argument | Popis |
|----------|--------|
| `--overpass-url` | Primární Overpass endpoint (default: ENV `OVERPASS_API_URL` nebo overpass-api.de) |
| `--overpass-fallback-url` | Fallback mirror (lze opakovat) |
| `--download-only` | Jen stáhnout JSON, neimportovat |
| `--save-json /cesta` | Uložit JSON (soubor nebo adresář `{region}_{timestamp}.json`) |
| `--query-debug` | Vypsat Overpass query |
| `--connect-timeout` | Default 15 s |
| `--read-timeout` | Default 180 s |
| `--max-retries` | Default 2 |
| `--sleep` | Pauza mezi regiony, default 8 s |
| `--split-bbox` | Velké regiony po dlaždicích |
| `--dry-run` | Validace bez zápisu do DB |
| `--test-overpass` | Malý test dotaz bez DB |

User-Agent: `SpravaVozidel/1.0 toozservis.cz toozservis@gmail.com`

---

## Ruční stažení JSON (když mirror na serveru nefunguje)

1. Na jiném stroji otevřete [Overpass Turbo](https://overpass-turbo.eu/) nebo použijte curl s funkčním mirror.
2. Query pro Svitavy viz níže.
3. Uložte JSON a nahrajte na server: `scp osm_svitavy.json server:/tmp/osm_import/`
4. Import: `--file /tmp/osm_import/osm_svitavy.json --batch-id osm-svitavy-manual-001`

### Overpass query – Svitavy test

```
[out:json][timeout:60];
(
  nwr["shop"="car_repair"](49.72,16.35,49.82,16.55);
  nwr["shop"="tyres"](49.72,16.35,49.82,16.55);
  nwr["craft"="mechanic"](49.72,16.35,49.82,16.55);
  nwr["amenity"="vehicle_inspection"](49.72,16.35,49.82,16.55);
  nwr["service:vehicle:inspection"="yes"](49.72,16.35,49.82,16.55);
  nwr["service:vehicle:tyres"="yes"](49.72,16.35,49.82,16.55);
  nwr["service:vehicle:car_repair"="yes"](49.72,16.35,49.82,16.55);
  nwr["service:vehicle:hgv"="yes"](49.72,16.35,49.82,16.55);
  nwr["service:vehicle:body_repair"="yes"](49.72,16.35,49.82,16.55);
  nwr["car:repair"="yes"](49.72,16.35,49.82,16.55);
  nwr["car:tyres"="yes"](49.72,16.35,49.82,16.55);
);
out center tags;
```

---

## MDČR STK/SME

```bash
curl -X POST http://127.0.0.1:8010/admin-api/service-map/import/mdcr-stk-sme \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"payload": [{"source_external_id":"STK001","name":"STK Demo","lat":49.75,"lng":16.47,"category":"stk","city":"Svitavy"}]}'
```

MDČR má vyšší `confidence_score` (0.92) než OSM (0.55). Ověřené servisy (`verified_service`) se importem nepřepisují.

## Admin přehled

- `GET /admin-api/service-map/overview`
- `GET /admin-api/service-map/claims?claim_status=pending`
- `GET /admin-api/service-map/duplicates`
- `GET /admin-api/service-map/import-batches`

## Seed (jen staging)

```bash
/opt/toozhub2/.venv/bin/python scripts/seed_service_map_staging.py
```

Seed není produkční data celé ČR.
