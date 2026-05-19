# SERVICE OFFICE IMPLEMENTATION REPORT

Datum: 2026-05-19

## Verdikt

Implementace funkcniho servisniho ERP retezce nebyla v tomto kroku spustena. Proveden byl staging-only audit a priprava bezpecneho implementacniho planu.

Duvod: audit prokazal, ze aplikace uz obsahuje servisni workspace, prijem/service-cases, canonical intake, zakazky, nabidky, faktury, PDF, service access, VIN historii, fotky, audit a testy. Masivni implementace vsech fazi najednou by mela vysoke riziko duplicit a rozbiti existujicich vazeb servis-zakaznik-vozidlo-VIN.

## Staging potvrzeni

- pracovni cesta: `/opt/toozhub2-staging/app`
- branch: `feature/user-app-visual-reference-20260518`
- commit pri auditu: `287649c9460212d68a65782a5b16d77d07decbe9`
- environment: `staging`
- port: `8010`
- URL: `https://staging.hub.toozservis.cz`
- DB bez citlivych udaju: `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Produkce nebyla pouzita pro runtime ani deploy.

## Zmenene soubory

V tomto kroku byly pridany pouze dokumenty:
- `STAGING_SERVICE_OFFICE_AUDIT.md`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

Nebyl menen runtime kod, backend, DB ani frontend.

## Nove soubory

- `STAGING_SERVICE_OFFICE_AUDIT.md`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

## Migrace

Zadne nove migrace v tomto kroku.

Existujici relevantni migrace nalezene auditem:
- `alembic/versions/20260412_0012_service_work_orders.py`
- `alembic/versions/20260415_0014_service_quotes.py`
- `alembic/versions/20260417_0017_service_invoices.py`
- `alembic/versions/20260417_0018_vehicle_photo_assets.py`
- `alembic/versions/20260511_0036_service_payroll.py`
- `alembic/versions/20260516_0040_service_intake_case_extension.py`

## Nove endpointy

Zadne nove endpointy v tomto kroku.

## Upravené endpointy

Zadne endpointy nebyly upraveny.

## Nove UI prvky

Zadne nove UI prvky nebyly pridany.

## Vylepsene existujici UI prvky

Zadne runtime UI prvky nebyly meneny.

## Pouzite existujici funkce identifikovane pro dalsi faze

- Service shell: `web/service-shell.js`
- Service workspace API: `src/modules/vehicle_hub/routers_v1/service_workspace.py`
- Service cases API: `src/modules/vehicle_hub/routers_v1/service_workspace_cases.py`
- Canonical service intake: `src/modules/vehicle_hub/routers_v1/service_canonical.py`
- Service work orders: `src/modules/vehicle_hub/routers_v1/service_dashboard.py`
- Service invoices: `src/modules/vehicle_hub/routers_v1/service_invoices.py`
- Service records: `src/modules/vehicle_hub/routers_v1/service_records.py`
- Vehicle photos: `src/modules/vehicle_hub/routers_v1/vehicles.py` + `VehiclePhotoAsset`
- Service access: `src/modules/vehicle_hub/service_access.py`
- Audit: `src/modules/vehicle_hub/audit_log.py`
- Public VIN history: `src/server/routers/public_vehicle_history.py`
- PDF builders: `src/modules/vehicle_hub/reports/*`

## Funkce, ktere nebyly meneny

- auth/session/token/logout
- user app shell
- service shell runtime
- admin
- backend endpointy
- DB schema
- VIN decoder
- service/customer/vehicle access
- public/auth landing
- FakturyWeb/licencni platby

## Zname riziko

- Zadani odpovida vice nez jedne velke epice. Bez rozdeleni na male PR/rezy by hrozilo vytvoreni duplicitniho ERP systemu vedle existujiciho service workspace.
- `service_intake.py`, `service_workspace_cases.py` a `service_canonical.py` se castecne prekryvaji; dalsi vyvoj musi vybrat canonical smer a legacy endpointy jen zachovat kvuli kompatibilite.
- `ServiceWorkOrder` nema polozkovy model, coz je nutny predpoklad pro material/labor/CSV/fakturaci ze zakazky.
- Service invoices maji draft/issued/cancelled, ale ne plny payment ledger.
- Verejna VIN historie je citliva na unik osobnich dat; work-order close hook musi publikovat jen anonymizovana data.

## Dalsi doporuceny krok

Prvni implementacni PR/release by mel byt uzky a testovatelny:

1. Pridat `service_work_order_items` jako backward compatible tabulku.
2. Doplnit API pro CRUD polozek work orderu.
3. Doplnit endpoint `POST /api/service/vehicle-intake/{case_id}/create-work-order`.
4. Doplnit minimalni service shell UI pro prijem -> zakazka.
5. Pridat targeted testy:
   - servis bez opravneni nevidi cizi vozidlo.
   - servis s opravnenim vytvori service case.
   - service case vytvori work order.
   - work order ulozi labor/material/other item.
   - audit log se zapise.

Az pote ma smysl delat CSV import, fakturaci ze zakazky a uzavreni do VIN historie.
