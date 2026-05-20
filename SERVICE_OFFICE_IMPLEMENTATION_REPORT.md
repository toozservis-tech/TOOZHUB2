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

## Dodatek 2026-05-20: UI napojeni polozek zakazky

Navazujici staging-only rez napojil hotovy backend polozek zakazky do existujiciho `web/service-shell.js`. Nevznikl novy frontend ani druhy detail zakazky.

Upraveno:

- detail existujici servisni zakazky zobrazuje blok `Polozky zakazky`
- blok nacita server-side summary z `GET /api/v1/services/workspace/work-orders/{id}/summary`
- UI obsahuje tabulku polozek `Prace / Material / Ostatni`
- UI obsahuje souhrny `prace bez DPH`, `material bez DPH`, `ostatni bez DPH`, `DPH celkem`, `celkem s DPH`
- modal umi pridat/upravit polozku pres `POST/PATCH`
- odebrani polozky vola `DELETE` a necha backend provest soft-delete/audit
- po create/update/delete se summary znovu nacita ze serveru
- 403 chyba se zobrazuje jako jasna hlaska pro servisni opravneni
- doplnen helper `createWorkOrderFromIntake(intakeId)` pro existujici/future intake UI, napojeny na `POST /api/v1/services/workspace/vehicle-intakes/{id}/create-work-order`

Zmenene soubory v UI rezu:

- `web/service-shell.js`
- `web/service-shell.css`
- `tests/e2e/service-shell-fallback.helpers.ts`
- `tests/e2e/service-shell-work-order-flow.spec.ts`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

Backend, DB a migrace nebyly v tomto navazujicim UI rezu meneny.

## Dodatek 2026-05-20: CSV import dilu do zakazky

Navazujici staging-only rez doplnil CSV import dilu primo do existujicich polozek zakazky. Nevznikl novy modul zakazek ani druhy system polozek.

Upraveno:

- `service_work_order_items.source` podporuje hodnotu `csv`
- `service_work_order_items.note` je nove nullable pole pro poznamku z CSV
- nova auditni tabulka `service_work_order_csv_imports`
- preview endpoint detekuje oddelovac `;`, `,`, tabulator
- preview vraci sloupce, prvni radky, navrzene mapovani a validaci bez zapisu do DB
- import endpoint prijima CSV + mapovani + `skip_duplicates`
- validni radky se vkladaji jako `material` polozky do `service_work_order_items`
- nevalidni radky se preskakuji a vraci konkretni chyby s cislem radku
- duplicity ze starsich CSV importu se detekuji podle `work_order_id + code + name + quantity + sale_price_without_vat`
- import zapisuje `service_work_order_csv_imports` a global audit log
- service shell dostal tlacitko `Import CSV dilu`, preview modal, mapovani sloupcu a potvrzeni importu
- po importu se znovu nacita server-side summary

Zmenene soubory v CSV rezu:

- `src/modules/vehicle_hub/models.py`
- `src/modules/vehicle_hub/schema_management.py`
- `src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py`
- `alembic/versions/20260520_0042_service_work_order_csv_imports.py`
- `web/service-shell.js`
- `web/service-shell.css`
- `tests/api/test_service_work_order_items.py`
- `tests/e2e/service-shell-fallback.helpers.ts`
- `tests/e2e/service-shell-work-order-flow.spec.ts`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

Nove endpointy:

- `POST /api/v1/services/workspace/work-orders/{id}/csv/preview`
- `POST /api/v1/services/workspace/work-orders/{id}/csv/import`

Nova migrace:

- `20260520_0042_service_work_order_csv_imports`

Poznamka k uploadu: staging runtime nema `python-multipart`, proto endpointy zpracovavaji multipart telo uzce lokalnim parserem pouze pro tento CSV import. Nevznikl obecny file manager.

## Dodatek 2026-05-20: Viditelne vytvoreni zakazky z prijmu

Navazujici staging-only rez doplnil viditelne UI napojeni hotoveho endpointu `create-work-order` do existujiciho service shellu. Nevznikl novy modul prijmu vozidla.

Upraveno:

- service shell nacita existujici `GET /api/v1/services/workspace/service-cases/`
- v sekci `Prichozi rezervace` vznikl samostatny panel `Prijmy vozidel`
- prijem bez navazane zakazky zobrazuje tlacitko `Vytvorit zakazku`
- prijem s navazanou zakazkou zobrazuje `Otevrit zakazku`
- klik vola existujici helper `createWorkOrderFromIntake(intakeId)`
- helper vola `POST /api/v1/services/workspace/vehicle-intakes/{id}/create-work-order`
- UI blokuje opakovane kliknuti pres `creatingWorkOrderFromIntake`
- uspesne vytvoreni otevre existujici detail zakazky
- chyby 403/404/409/422 se prekladaji do srozumitelnych hlasek pro servisni pracovniky

Zmenene soubory v tomto rezu:

- `web/service-shell.js`
- `web/service-shell.css`
- `tests/e2e/service-shell-fallback.helpers.ts`
- `tests/e2e/service-shell-work-order-flow.spec.ts`
- `SERVICE_OFFICE_IMPLEMENTATION_REPORT.md`
- `SERVICE_OFFICE_TEST_REPORT.md`

Backend, DB, migrace a produkce nebyly v tomto rezu meneny.

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
- `POST /work-orders/{id}/csv/preview`
- `POST /work-orders/{id}/csv/import`

## Upravené endpointy

Zadne existujici API kontrakty nebyly zmeneny.

## Nove UI prvky

Backendovy rez z 2026-05-19 runtime UI nemenil. Navazujici UI rez z 2026-05-20 doplnil do existujiciho service shellu:

- blok `Polozky zakazky` v detailu zakazky
- tlacitka `Pridat praci`, `Pridat material`, `Pridat ostatni`
- modal pro pridani/upravu polozky
- akce `Upravit` a `Odebrat`
- server-side souhrn cen v detailu zakazky
- modal `Import CSV dilu` s uploadem, nahledem, mapovanim sloupcu, validaci a potvrzenim importu

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
- Tlacitko `Vytvorit zakazku` z prijmu je pripraveno jako helper `createWorkOrderFromIntake(intakeId)`, ale nebylo vlozeno do konkretniho intake detailu, protoze v aktualnim service shellu nebyl nalezen samostatny existujici detail prijmu vozidla.
- U CSV importu se zatim neukladaji opakovane mapovaci sablony; to je vedomy limit podle zadani.
- Fakturace ze zakazky a uzavreni do VIN historie nejsou soucasti tohoto rezu.

## Dalsi doporuceny krok

1. Doplnit viditelne intake detail UI, pokud bude v service shellu potvrzene jeho misto.
2. Doplnit ulozene mapovaci sablony CSV, pokud se ukaze opakovany format dodavatelu.
3. Potom pripravit fakturaci ze zakazky.
