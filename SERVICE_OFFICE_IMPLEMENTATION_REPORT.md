# SERVICE OFFICE IMPLEMENTATION REPORT

Datum: 2026-05-19

## Verdikt

Tento rez doplnil prvni bezpecny implementacni clanek servisniho retezce:

- polozky servisni zakazky `labor/material/other`
- server-side vypocet ceny bez DPH / DPH / s DPH
- vytvoreni servisni zakazky z existujiciho prijmu `ServiceIntake`
- audit polozek a konverze prijmu na zakazku
- targeted backend testy

Nevznikl druhy ERP system. Implementace rozsiruje existujici `ServiceWorkOrder`, `ServiceIntake`, `VehicleServiceLink`, `ServiceCustomerLink` a globalni audit log.

## Staging potvrzeni

- pracovni cesta: `/opt/toozhub2-staging/app`
- branch: `feature/user-app-visual-reference-20260518`
- environment: `staging`
- port: `8010`
- DB bez citlivych udaju: `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Produkce nebyla pouzita pro runtime, DB ani deploy.

## Zmenene soubory

- `src/modules/vehicle_hub/models.py`
- `src/modules/vehicle_hub/routers_v1/__init__.py`
- `src/modules/vehicle_hub/schema_management.py`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

## Nove soubory

- `alembic/versions/20260519_0041_service_work_order_items.py`
- `src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py`
- `tests/api/test_service_work_order_items.py`

## Migrace

- `20260516_0041_staging_revision_compat.py`
- `20260519_0041_service_work_order_items.py`

Nova tabulka:

- `service_work_order_items`

Poznamka: staging DB uz byla pred timto rezem oznacena revizi `20260516_0041`, ktera nebyla v checkoutu pritomna. Byl proto doplnen no-op compatibility marker `20260516_0041_staging_revision_compat.py`, aby byl migracni retezec resolvovatelny bez zmen schématu. Realnou schema zmenu dela az `20260519_0041_service_work_order_items.py`.

Sloupce:

- `work_order_id`
- `item_type`
- `name`
- `code`
- `quantity`
- `unit`
- `vat_rate`
- `purchase_price_without_vat`
- `sale_price_without_vat`
- `discount_percent`
- `mechanic_id`
- `source`
- `created_by`
- `created_at`
- `updated_at`
- `deleted_at`
- `deleted_by`

## Nove endpointy

Vsechny pod `/api/v1/services/workspace`:

- `POST /work-orders/{id}/items`
- `PATCH /work-orders/{id}/items/{item_id}`
- `DELETE /work-orders/{id}/items/{item_id}`
- `GET /work-orders/{id}/summary`
- `POST /vehicle-intakes/{id}/create-work-order`

## Upravené endpointy

Zadne existujici API kontrakty nebyly zmeneny.

## Nove UI prvky

Zadne runtime UI prvky v tomto rezu nebyly pridany. Service shell zustal beze zmen, protoze tento krok resil nejdriv stabilni datovy/API zaklad. UI napojeni bloku "Polozky zakazky" je dalsi maly navazujici rez.

## Pouzite existujici funkce

- `ServiceIntake` jako prijem vozidla
- `ServiceWorkOrder` jako existujici zakazka
- `VehicleServiceLink` pres `require_approved_service_vehicle_access`
- `ServiceCustomerLink` jako aktivni vazba servis-zakaznik
- `_require_service_workspace_role` pro servisni workspace guard
- `write_global_audit_log` pro audit zmen polozek a konverze prijmu
- `ServiceWorkOrderAuditLog` pro audit vytvoreni zakazky z prijmu
- `assert_module_ready` pro readiness guardy

## Funkce, ktere nebyly meneny

- auth/session/token/logout
- public/auth landing
- user app shell
- service shell runtime
- admin
- VIN decoder
- service/customer/vehicle access semantics
- service invoices
- quotes
- service records / public VIN history
- produkcni service ani produkcni DB

## Zname limity

- Stavovy workflow zakazek zustava v existujicim rozsahu `awaiting_client_approval/approved/in_progress/completed/issue`.
- `mechanic_id` je pripraveny nullable field, ale plne napojeni na service employees/payroll prijde v dalsim rezu.
- UI pro pridavani polozek v service shellu jeste neni napojene.
- CSV import, fakturace ze zakazky a uzavreni do VIN historie nejsou soucasti tohoto rezu.

## Dalsi doporuceny krok

1. Spustit migraci na staging DB.
2. Minimalne napojit existujici detail zakazky v `web/service-shell.js` na summary a CRUD polozek.
3. Potom udelat CSV preview/import jako navazujici zdroj `material` polozek.
