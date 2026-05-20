# SERVICE OFFICE TEST REPORT

Datum: 2026-05-19

## Runtime safety

Overeno pred implementaci:

- `pwd` => `/opt/toozhub2-staging/app`
- branch => `feature/user-app-visual-reference-20260518`
- staging service => `toozhub2-staging.service` active
- health endpoint => OK
- DB => `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Produkce nebyla pouzita ani restartovana.

## Testovaci prikazy

```bash
python3 -m py_compile src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py
python3 -m py_compile src/modules/vehicle_hub/models.py src/modules/vehicle_hub/routers_v1/__init__.py
alembic upgrade head
alembic current
python3 -m pytest tests/api/test_service_work_order_items.py
python3 -m pytest tests/api/test_service_cases_api.py tests/api/test_service_dashboard.py
```

## Vysledky

- `py_compile service_workspace_work_orders.py`: PASS
- `py_compile models.py __init__.py`: PASS
- `alembic upgrade head`: PASS, staging DB upgraded to `20260519_0041`
- `alembic current`: PASS, `20260519_0041 (head)`
- `tests/api/test_service_work_order_items.py`: PASS, 8 passed
- `tests/api/test_service_cases_api.py tests/api/test_service_dashboard.py`: PASS, 10 passed

## Dodatek 2026-05-20: UI napojeni service shellu

Runtime safety:

- `pwd` => `/opt/toozhub2-staging/app`
- branch => `feature/user-app-visual-reference-20260518`
- staging service => `toozhub2-staging.service` active
- health endpoint => OK, `environment=staging`
- DB => `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Testovaci prikazy:

```bash
node --check web/service-shell.js
python3 -m pytest tests/api/test_service_work_order_items.py
BASE_URL=http://127.0.0.1:8010 npx playwright test service-shell-work-order-flow.spec.ts --config=playwright.config.ts --workers=1 --retries=0 --reporter=line
```

Vysledky:

- `node --check web/service-shell.js`: PASS
- `tests/api/test_service_work_order_items.py`: PASS, 8 passed
- `service-shell-work-order-flow.spec.ts`: PASS, 1 passed proti staging portu `8010`

Pokryte UI scenare:

- detail zakazky nacte blok `Polozky zakazky`
- prazdna zakazka ukaze empty state
- pridani prace vola backend POST endpoint
- po pridani se zobrazi server-side summary a cena s DPH
- odebrani polozky vola DELETE endpoint a obnovi summary
- 403 z item endpointu zobrazi hlasku `Servis nema opravneni k teto zakazce/vozidlu.`
- `createWorkOrderFromIntake(321)` vola `POST /api/v1/services/workspace/vehicle-intakes/321/create-work-order` a otevre detail vytvorene zakazky
- existujici create/update flow zakazky zustal funkcni
- test bezi proti staging URL, ne proti portu produkce

## Pokryte scenare

- vytvoreni work order z `ServiceIntake`
- ulozeni polozky prace
- ulozeni polozky materialu
- ulozeni ostatni polozky
- summary po skupinach `labor/material/other`
- vypocet DPH a celku server-side
- cizi servis nemuze upravit zakazku jineho servisu
- smazani polozky je soft-delete
- soft-delete polozky zapisuje audit
- ne-servisni uzivatel dostane 403
- existujici service-cases API zustalo funkcni
- existujici service dashboard API zustalo funkcni

## Nespustene testy

Siroke full-suite E2E nebyly spusteny. Tento rez overil pouze targeted service-shell flow a backend testy polozek zakazky.

## Dalsi testy pro navazujici rezy

- zmena a soft-delete polozky pres UI
- pridani materialu a ostatni polozky pres UI
- vytvoreni zakazky z konkretniho intake detailu, az bude potvrzene misto v service shellu
- mobil/tablet smoke pro service shell
