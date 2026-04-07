# Technický backlog přejmenování (legacy identifikátory)

Cíl: postupně odstranit historické názvy **TooZHub2 / TOOZHUB2 / TooZ Hub** z technické vrstvy bez výpadku provozu.

| Oblast | Současný stav | Priorita | Riziko | Doporučený postup |
|--------|----------------|----------|--------|-------------------|
| GitHub repozitář | Remote `toozservis-tech/TOOZHUB2` | Střední | Vysoké (CI, lokální remote, odkazy) | Přejmenovat repo v GitHub UI, aktualizovat `origin`, dokumentaci a výchozí `GITHUB_REPOSITORY`; dočasně redirect GitHub obvykle zachová. |
| Env proměnné | `TOOZHUB_API_URL`, `TOOZHUB_ADMIN_*` | Střední | Střední (prod .env) | Zavést aliasy `SPRAVA_VOZIDEL_*`, v kódu číst obojí s preferencí nového názvu; po migraci smazat staré. |
| iOS target / modul | `TooZHubiOS`, `TooZHub` sources, PRODUCT_NAME | Vysoká | Vysoká (signing, App Store) | Přejmenovat v `project.yml` / Xcode, aktualizovat bundle ID ve vývojářském účtu, nová build konfigurace. |
| Python balíček / moduly | `src.modules.vehicle_hub`, import cesty | Nízká | Velmi vysoká | Neprovádět slepě; případně zavést tenký facade package a postupně přesouvat. |
| systemd / Windows úlohy | Dokumentace už používá `SpravaVozidel-*`; na serverech mohou běžet staré názvy úloh | Střední | Střední | Na každém hostu přejmenovat úlohy a skripty podle runbooku; ověřit po restartu. |
| Databáze / migrace | Žádný povinný sloupec s názvem produktu typicky neblokuje | Nízká | Nízká | Pouze pokud by existovaly řetězce v tabulkách – čistit datově odděleně. |
| Web push zpráva (legacy) | `TOOZHUB_NOTIFICATION_CLICK` ještě přijímáno v `web/index.html` | Nízká | Nízká | Po několika releasích odebrat fallback, až metrika ukáže nulové staré SW. |
| Lokální cesty v docs | Část návodů používá `sprava-vozidel` místo historického `TOOZHUB2` | Nízká | Nízká | Sjednotit s reálnou cestou na discích vývojářů. |

## Bezpečně už provedeno (nízké riziko)

- HTTP `Server` token, externí `User-Agent` řetězce volající třetí API.
- Veřejné API metadata (`FastAPI.title`, část health JSON).
- Zobrazované názvy v e-mail šablonách (přes `APP_DISPLAY_NAME`).

## Ověření po změnách

```bash
cd /cesta/k/projektu
python -c "from src.server.main import app; print(app.title)"
```

Očekáváno: titulek obsahuje „Správa vozidel API“ (nebo ekvivalent z `branding`).
