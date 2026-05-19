# SERVICE OFFICE TEST REPORT

Datum: 2026-05-19

## Provedene kontroly

Safety/runtime:
- `pwd`
- `git branch --show-current`
- `git rev-parse HEAD`
- `git status --short`
- `systemctl is-active toozhub2-staging.service`
- `curl -fsS http://127.0.0.1:8010/health`
- `grep -E "DATABASE_URL|APP_ENV|ENVIRONMENT|PORT|DOMAIN|BASE_URL|PUBLIC_URL" .env`

Vysledek:
- path: `/opt/toozhub2-staging/app`
- branch: `feature/user-app-visual-reference-20260518`
- service: `toozhub2-staging.service` active
- health: OK
- environment: `staging`
- port: `8010`
- DB: `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Audit commands:
- `rg --files src web tests alembic docs`
- `rg -n "serviceWorkspace|service shell|service-shell|vehicle-access|work_order|reservation|intake|invoice|faktur|payment|pdf|audit|tenant|permission|VIN|vin|upload|photo|image|history|record" src web tests alembic docs -S`
- targeted reads of:
  - `src/modules/vehicle_hub/routers_v1/service_intake.py`
  - `src/modules/vehicle_hub/routers_v1/service_workspace.py`
  - `src/modules/vehicle_hub/routers_v1/service_canonical.py`
  - `src/modules/vehicle_hub/routers_v1/service_workspace_cases.py`
  - `src/modules/vehicle_hub/routers_v1/service_dashboard.py`
  - `src/modules/vehicle_hub/routers_v1/service_invoices.py`
  - `src/modules/vehicle_hub/routers_v1/service_records.py`
  - `src/modules/vehicle_hub/models.py`
  - `src/modules/vehicle_hub/schema_management.py`
  - `web/service-shell.js`
  - `web/service-shell.css`
  - relevant tests under `tests/api` and `tests/e2e`.

## Testy nespustene

Runtime kod nebyl menen, proto nebyly spusteny backend/e2e regresni testy. V tomto kroku vznikly pouze dokumenty.

Pred prvni implementacni zmenou doporucuji spustit minimalne:

```bash
pytest tests/api/test_service_cases_api.py
pytest tests/api/test_service_dashboard.py
pytest tests/api/test_service_invoices.py
pytest tests/api/test_service_full_user_visible_flow.py
pytest tests/api/test_public_vehicle_history_qr.py
pytest tests/api/test_vehicle_owner_data_minimization.py
node --check web/service-shell.js
npx playwright test tests/e2e/service-shell-work-order-flow.spec.ts
npx playwright test tests/e2e/service-shell-invoice-flow.spec.ts
npx playwright test tests/e2e/service-real.auth-smoke.spec.ts
```

## Ocekavany test plan pro budouci implementaci

Backend:
- servis bez opravneni nevidi cizi vozidlo.
- servis s opravnenim vytvori prijem/service case.
- prijem umi ulozit fotky podle povolenych `photo_kind`.
- fotky maji `sha256_hex` a vazbu na `vehicle_id`, `related_case_id`, tenant a service uploader.
- prijem vytvori zakazku pres `source_intake_id`.
- zakazka umi labor/material/other polozky.
- CSV preview detekuje oddelovac.
- CSV import vlozi validni material polozky a preskoci vadne radky.
- import zapise audit a hash souboru.
- zamestnanec/mechanik se da priradit k praci.
- faktura vznikne ze zakazky a prevezme polozky.
- faktura vygeneruje PDF.
- faktura jde oznacit jako uhrazena bez pouziti licencnich plateb.
- uzavrena zakazka vytvori servisni zaznam.
- public VIN historie neobsahuje osobni udaje.

Frontend smoke:
- service login.
- otevreni staging service workspace.
- novy prijem vozidla.
- nahrani fotky.
- vytvoreni zakazky.
- pridani labor/material polozky.
- CSV import.
- vytvoreni faktury.
- PDF faktury.
- uzavreni zakazky.
- kontrola historie vozidla.

## Aktualni vysledek

PASS pro staging safety a audit.

FAIL/PENDING pro plnou implementaci servisniho retezce, protoze v tomto kroku nebyl menen runtime kod. Implementace ma pokracovat v malych navazujicich fazich podle auditu.
