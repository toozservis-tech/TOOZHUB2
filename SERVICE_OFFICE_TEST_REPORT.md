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

E2E service shell testy nebyly spusteny, protoze v tomto rezu nebylo meneno runtime UI.

## Dalsi testy pro navazujici UI rez

- service login
- otevreni detailu zakazky
- zobrazeni polozek zakazky
- pridani prace/materialu/ostatni polozky pres UI
- zmena a soft-delete polozky pres UI
- kontrola souhrnu cen v UI
- mobil/tablet smoke pro service shell
