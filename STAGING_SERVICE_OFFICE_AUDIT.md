# STAGING SERVICE OFFICE AUDIT

Datum: 2026-05-19

Runtime overeni:
- path: `/opt/toozhub2-staging/app`
- branch: `feature/user-app-visual-reference-20260518`
- HEAD pri auditu: `287649c9460212d68a65782a5b16d77d07decbe9`
- environment: `staging`
- port: `8010`
- URL: `https://staging.hub.toozservis.cz`
- DB: `sqlite:////opt/toozhub2-staging/data/vehicles_staging.db`

Verdikt: projekt uz ma velkou cast servisniho retezce hotovou. Neni bezpecne vytvaret druhy servisni system vedle stavajiciho. Dalsi prace ma byt mala navazujici evoluce existujicich modulu.

## Existujici moduly a soubory

### Service workspace / servisni UI
- `web/service-shell.js`: service shell s dashboardem, zakazniky, vozidly, zakazkami, dokumenty, fakturami, rezervacemi, pripominkami, zamestnanci/mzdami a nastavenim. Obsahuje `openCreateWorkOrderModal`, `openReservationDetailModal`, `openCreateInvoiceModal`, `openServiceInvoiceDetailModal`, `openServiceInvoicePdf`.
- `web/service-shell.css`: hotovy styl service shellu, vcetne fakturacnich editoru a responsivnich pravidel.
- `src/modules/vehicle_hub/routers_v1/service_workspace.py`: servisni workspace API pro klienty, vyhledani vozidla, propojeni se zakaznikem, pozvanky, doklady, reminders, QR a detail vozidla.
- `src/modules/vehicle_hub/routers_v1/service_workspace_customer_centre.py`: centrum zakazniku a linkovani pres lookup.

Pouzitelne beze zmen:
- navigace service shellu
- zakaznicke vazby
- discovery/linkovani servis-zakaznik
- service access a schvaleni pristupu k vozidlu
- UI pro zakazky, faktury, rezervace a dokumenty jako zaklad.

Riziko:
- `web/service-shell.js` je centralni a dlouhy soubor. Kazda uprava muze ovlivnit komplet service UI.

### Propojeni servis-zakaznik-vozidlo
- `src/modules/vehicle_hub/models.py`: `ServiceCustomerLink`, `ServiceVehicleAccess`, `VehicleServiceLink`, `VehicleOwnership`.
- `src/modules/vehicle_hub/service_access.py`: canonical service access helpers, lookup, masked VIN/SPZ, approved link, permission checks.
- `src/modules/vehicle_hub/routers_v1/services.py`: user-facing service access, discovery, requests, `vehicle-access`.
- `src/modules/vehicle_hub/routers_v1/service_workspace.py`: service-facing lookup/detail/access.
- `src/modules/vehicle_hub/routers_v1/vehicle_lifecycle.py`: service access lifecycle nad vozidlem.

Pouzitelne beze zmen:
- existing permission guardy
- schvalovani pristupu k vozidlu
- maskovani VIN/SPZ u neschvaleneho pristupu
- owner/source-of-truth pres `VehicleOwnership`.

Nesmi se menit:
- permission semantics v `service_access.py`
- vazby `VehicleOwnership`, `ServiceVehicleAccess`, `VehicleServiceLink`
- ochrana osobnich dat pri service lookup.

### VIN lookup / decoder
- `src/modules/vehicle_hub/routers_v1/vehicles.py`: `POST /api/v1/vehicles/preview-from-vin`, ORV parser, photo upload, tachometer/STK history.
- `src/modules/vehicle_hub/routers_v1/vin_lookup.py`: VIN lookup endpoint.
- `src/modules/vehicle_hub/decoder/*`: VIN/SPZ decoder, MDCR/open data klienti, validator, data maps.
- `src/modules/vehicle_hub/api_vin.py`: VIN service support.

Pouzitelne beze zmen:
- VIN preview/decode
- ORV scan
- tachometer/STK history.

Nesmi se menit:
- VIN decoder nenahrazovat druhym dekoderem.

### Vozidla, fotky, uploady
- `src/modules/vehicle_hub/models.py`: `Vehicle`, `VehiclePhoto`, `VehiclePhotoAsset`, `ServiceRecord`.
- `src/modules/vehicle_hub/routers_v1/vehicles.py`: `/photos`, `/photo`, `/photo/promote`.
- `src/modules/vehicle_hub/routers_v1/service_records.py`: attachments upload/download pro servisni zaznamy.
- `src/modules/vehicle_hub/routers_v1/service_canonical.py`: `POST /api/service/vehicle-intake/{case_id}/upload-photos`, uklada do `VehiclePhotoAsset`, vcetne `related_case_id`, `photo_kind`, `sha256_hex`, `vin`.

Pouzitelne beze zmen:
- `VehiclePhotoAsset` jako source of truth pro nove fotky.
- hash fotek `sha256_hex`.
- navazani fotek na `service_intakes` pres `related_case_id`.

Rozdelane:
- intake photo kinds jsou zatim obecne: `primary_thumbnail`, `intake_overview`, `damage_evidence`, `repair_area_before`, `repair_area_after`, `document_scan`, `other`.
- pozadovane druhy fotek prijmu (`front`, `rear`, `left`, `right`, `interior`, `odometer`, `damage`, `other`) nejsou samostatne povolene v canonical endpointu.

### Prijem vozidla / service cases
- `src/modules/vehicle_hub/models.py`: `ServiceIntake`, `ServiceLaborSession`.
- `src/modules/vehicle_hub/routers_v1/service_intake.py`: legacy `/api/v1/service/intake`; nema vsechny aktualni vazby a je mene vhodny pro dalsi rozvoj.
- `src/modules/vehicle_hub/routers_v1/service_workspace_cases.py`: `/api/v1/services/workspace/service-cases`, fasada nad `ServiceIntake`, vytvori case jen pri schvalenem service-vehicle access.
- `src/modules/vehicle_hub/routers_v1/service_canonical.py`: `/api/service/vehicle-intake/from-spz-photo`, owner access request, photo upload, start/stop work, create service record, assigned/search vehicles.

Pouzitelne beze zmen:
- service-cases API jako bezpecna fasada pro bezny prijem.
- canonical intake pro SPZ/photo, owner access request, labor timer a final service record.
- audit pres `write_global_audit_log`.

Rozdelane:
- chybi PDF prijmoveho protokolu.
- chybi UI pro plny prijem v service shellu.
- chybi konverze service case -> work order primo v API.
- chybi explicitni stav paliva; legacy `fluids_ok` je JSON/text, ale neni first-class fuel level.

### Zakazky / work orders
- `src/modules/vehicle_hub/models.py`: `ServiceWorkOrder`, `ServiceWorkOrderAuditLog`.
- `src/modules/vehicle_hub/routers_v1/service_dashboard.py`: `/api/service/work-orders`, detail, create, update, duplicate guard.
- `web/service-shell.js`: `openCreateWorkOrderModal`, `workOrdersSection`, detail work order modal.

Pouzitelne beze zmen:
- zakladni work order list/detail/create/update.
- audit log work orderu.
- vazba na rezervaci, dokument i intake.

Chybi uplne:
- tabulka/detailni model polozek zakazky `labor/material/other`.
- samostatne polozky materialu s nakupni/prodejni cenou, DPH, slevou, marzi.
- stavovy workflow podle zadani (`new`, `intake`, `diagnostic`, ...).
- km pri predani jako work-order field; je pouze v `ServiceIntake.mileage_out`.

### Nabidky / quotes
- `src/modules/vehicle_hub/models.py`: `ServiceQuote`, `ServiceQuoteAuditLog`, access tokens/logs.
- `src/modules/vehicle_hub/routers_v1/service_dashboard.py`: `/api/service/quotes`, `/quotes/from-record/{record_id}`, `/quotes/{quote_id}/pdf`.
- `src/server/routers/public_quote.py`: public quote access.
- `web/service-shell.js`: quote UI napojene na service shell.

Pouzitelne beze zmen:
- nabidka z recordu.
- PDF nabidky.
- public approve/reject flow.

Rozdelane:
- quote items jsou JSON, nejsou sdilene se zamyslenymi work-order items.

### Faktury / platby / PDF
- `src/modules/vehicle_hub/models.py`: `ServiceInvoice`, `ServiceInvoiceLine`, `ServiceInvoiceCounter`, `ServiceFakturywebSettings`, `ServiceFakturywebInvoice`.
- `src/modules/vehicle_hub/routers_v1/service_invoices.py`: `/api/service/invoices`, issue/cancel/pdf, FakturyWeb export/sync.
- `src/modules/vehicle_hub/reports/service_invoice_pdf.py`: internal service invoice PDF.
- `web/service-shell.js`: invoice editor, line editor, detail modal, PDF open.

Pouzitelne beze zmen:
- draft/issued/cancelled faktury.
- line items.
- PDF.
- FakturyWeb export/sync.
- vazba na `work_order_id`, `service_record_id`, `vehicle_id`, `customer_id`.

Rozdelane:
- neni first-class `payment_status` pro servisni fakturu (`unpaid`, `partially_paid`, `paid`).
- neni `paid_amount`, `paid_at`, payment ledger pro servisni faktury.
- QR platba v lokalnim service invoice neni jasne samostatne ulozena.
- dobropis/storno je UI volba v editoru, ale lokalni backend ma hlavne `cancel`; chybi plny credit-note model/vazba.

Nesmi se zamichat:
- licencni platby v `license_status.py` jsou jiny domenovy problem a nesmi se pouzit jako servisni fakturace.

### CSV import / sklad
- `src/modules/vehicle_hub/routers_v1/service_workspace.py`: dokumentovy ingest umi PDF/foto/text/csv extrakci textu a auto service record.
- `src/modules/vehicle_hub/routers_v1/service_canonical.py`: `/api/service/inventory/import-delivery-note` je auditni stub.
- `src/modules/vehicle_hub/routers_v1/part_orders.py`: CRUD pro part orders, ale ne plny sklad/CSV import do zakazky.

Chybi uplne:
- CSV preview endpoint.
- delimiter detection + column mapping.
- mapping templates.
- import audit tabulka pro CSV.
- insert material polozek do work orderu.
- duplicate protection nad importem.

### Zamestnanci servisu / mechanici
- `src/modules/vehicle_hub/routers_v1/service_dashboard.py`: work orders maji `technician_id`, `/api/service/technicians/performance`.
- `web/service-shell.js`: sekce Zamestnanci/Dochazka/Mzdy pres `/api/service/payroll/*`.
- migrace `20260511_0036_service_payroll.py`.

Pouzitelne beze zmen:
- payroll/employee UI a API jako zaklad seznamu zamestnancu.
- `technician_id` u work orderu.

Rozdelane:
- neni potvrzeno, ze payroll employee = servisni subucet/opravneny mechanik pro zakazky.
- role `reception/mechanic/warehouse/accountant` nejsou potvrzene jako service permission model.

### VIN historie / verejny vypis
- `src/modules/vehicle_hub/routers_v1/service_records.py`: create/update/delete service records, attachments, PDF/export.
- `src/modules/vehicle_hub/service_record_snapshot.py`: snapshot/hash servisnich zaznamu.
- `src/modules/vehicle_hub/reports/vehicle_report_builder.py`
- `src/modules/vehicle_hub/reports/vehicle_report_pdf.py`
- `src/modules/vehicle_hub/vehicle_public_history.py`
- `src/server/routers/public_vehicle_history.py`
- `tests/api/test_public_vehicle_history_qr.py`
- `tests/api/test_vehicle_owner_data_minimization.py`

Pouzitelne beze zmen:
- finalni servisni zaznamy jsou zdroj VIN historie.
- public QR/token flow.
- minimalizace osobnich dat je uz testovana.

Rozdelane:
- uzavreni work orderu nevypada jako jednotny trigger pro vytvoreni final service record.
- canonical intake umi `create-service-record`, ale work-order completed -> VIN history record neni sjednocene.

### Audit log a permission logika
- `src/modules/vehicle_hub/audit_log.py`: `write_global_audit_log`.
- `src/modules/vehicle_hub/models.py`: `GlobalAuditLog`, `ServiceRecordAuditLog`, `ServiceWorkOrderAuditLog`, `ServiceQuoteAuditLog`.
- `src/modules/vehicle_hub/schema_management.py`: readiness guards pro `service_workspace`, `service_dashboard`, `service_invoices`, `service_records`, `reservations`.
- `src/modules/vehicle_hub/workspace_entitlements.py`
- `src/core/rbac.py`

Pouzitelne beze zmen:
- global audit.
- module readiness guards.
- service workspace entitlement.

Riziko:
- u noveho kodu je nutne pouzit existujici guardy a audit, jinak vznikne bypass vedle hotove permission vrstvy.

## Co je pouzitelne beze zmen

- service shell jako primarni servisni frontend.
- service/customer/vehicle access flow.
- VIN lookup/preview/decode.
- vehicle photo assets a hash.
- service case fasada pro prijem.
- canonical intake endpoints pro SPZ/photo, owner request, photo upload, labor timer, final service record.
- work order list/create/update/detail.
- service quotes + PDF.
- service invoices + PDF.
- service records + attachments + PDF/export.
- public vehicle history a QR tokeny.
- global audit log.
- readiness guards.
- existujici testy pro service cases, invoices, dashboard, quotes, public history, owner data minimization.

## Co je rozdelane a potrebuje dokoncit

- sjednoceni `service_intake.py` legacy API s novejsimi `service_workspace_cases.py` a `service_canonical.py`.
- plny prijemovy formular v service shellu.
- intake PDF protokol.
- intake -> work order endpoint.
- work order status map na zadany cilovy workflow.
- work order item model pro labor/material/other.
- CSV import do work-order material items.
- payment status pro servisni faktury.
- work-order close -> service record/VIN history canonical trigger.
- propojeni payroll employees/subaccounts do mechanic assignment.

## Co chybi uplne

- `service_work_order_items` nebo ekvivalent.
- `service_work_order_item_imports`/CSV import audit.
- `service_csv_mapping_templates`.
- `service_invoice_payments` nebo payment ledger pro lokalni servisni fakturaci.
- intake protocol PDF endpoint.
- plny skladovy modul v rozsahu IC Office.

## Co se nesmi menit

- nazev aplikace: pouze `Správa vozidel`.
- produkcni cesta `/opt/toozhub2/app`.
- produkcni DB.
- existujici API kontrakty bez zpetne kompatibility.
- `service_access.py` bez zvlastniho auditu.
- VIN decoder.
- vehicle ownership/source-of-truth.
- public VIN history privacy.
- existujici user/service/admin auth a token/session logika.
- licencni platby jako nahrada servisni fakturace.

## Kde chybi propojeni

- service case -> work order.
- work order -> itemized material/labor/other.
- CSV import -> work order material items.
- work order completion -> final `ServiceRecord`.
- service invoice payment status -> work order/invoice closure.
- employee/payroll subaccount -> mechanic role in work order item/labor session.
- intake photos with exact required kinds -> `VehiclePhotoAsset.photo_kind`.

## Rizika rozbiti existujici funkce

- rozsirovani `web/service-shell.js` muze rozbit celou servisni navigaci.
- nove endpointy mimo existing guards by mohly obejit service/customer/vehicle permission model.
- pridani work-order item modelu musi byt nullable/backward compatible, protoze existujici work orders jsou bez polozek.
- public VIN historie nesmi dostat osobni data z invoice/customer linku.
- uzavreni zakazky nesmi duplikovat servisni zaznam, pokud uz vznikl z intake nebo rucne.

## Minimalni zmeny navrzene pro prvni implementacni rez

1. Rozsirit `ServiceIntake`/service-cases bez nove tabulky:
   - pridat explicitni `fuel_level_percent` nullable.
   - rozsirit povolene `photo_kind` v canonical uploadu o `front`, `rear`, `left`, `right`, `interior`, `odometer`, `damage`.
   - pridat endpoint intake protocol PDF pres existujici report/PDF utility.
2. Pridat `POST /api/service/vehicle-intake/{case_id}/create-work-order`:
   - pouzit existujici `ServiceWorkOrder`.
   - naplnit `source_intake_id`.
   - auditovat.
   - bez noveho paralelniho modelu.
3. Pridat novou tabulku `service_work_order_items`:
   - vazba na `service_work_orders`.
   - item_type `labor/material/other`.
   - ceny nullable/default 0.
   - tenant/service/work_order indexy.
4. Pridat CSV preview/import jako navazujici endpointy az po item modelu:
   - preview bez zapisu.
   - import do `service_work_order_items`.
   - audit + hash puvodniho souboru.
5. Doplnit service shell UI postupne:
   - Prijem vozidla.
   - Detail zakazky s polozkami.
   - CSV import modal.

## Presny seznam souboru pro prvni bezpecny rez

Backend:
- `src/modules/vehicle_hub/models.py`
- nova migrace v `alembic/versions/`
- `src/modules/vehicle_hub/schema_management.py`
- `src/modules/vehicle_hub/routers_v1/service_canonical.py`
- `src/modules/vehicle_hub/routers_v1/service_dashboard.py`
- pripadne novy helper `src/modules/vehicle_hub/service_work_order_items.py`

Frontend:
- `web/service-shell.js`
- `web/service-shell.css`

Tests:
- `tests/api/test_service_cases_api.py`
- `tests/api/test_service_dashboard.py`
- novy test `tests/api/test_service_work_order_items.py`
- novy test `tests/api/test_service_csv_import.py`
- e2e doplnek k `tests/e2e/service-real.auth-smoke.spec.ts` nebo novy `tests/e2e/service-shell-intake-work-order.spec.ts`

## Testovaci plan

Safety:
- `pwd`
- `git branch --show-current`
- `git rev-parse HEAD`
- `grep -E "DATABASE_URL|APP_ENV|ENVIRONMENT|PORT|PUBLIC_API_BASE_URL|FRONTEND_BASE_URL" .env`
- `curl -fsS http://127.0.0.1:8010/health`

Backend targeted:
- `pytest tests/api/test_service_cases_api.py`
- `pytest tests/api/test_service_dashboard.py`
- `pytest tests/api/test_service_invoices.py`
- `pytest tests/api/test_service_full_user_visible_flow.py`
- `pytest tests/api/test_public_vehicle_history_qr.py`
- `pytest tests/api/test_vehicle_owner_data_minimization.py`

Frontend syntax/smoke:
- `node --check web/service-shell.js`
- `npx playwright test tests/e2e/service-shell-work-order-flow.spec.ts`
- `npx playwright test tests/e2e/service-shell-invoice-flow.spec.ts`
- `npx playwright test tests/e2e/service-real.auth-smoke.spec.ts`

Manual staging:
- service login.
- otevrit service workspace.
- vyhledat vozidlo pres SPZ/VIN.
- zalozit intake.
- nahrat fotky prijmu.
- z intake vytvorit zakazku.
- pridat labor/material item.
- importovat CSV.
- vytvorit fakturu ze zakazky.
- vystavit PDF.
- oznacit uhradu.
- uzavrit zakazku.
- overit servisni zaznam v historii vozidla.
- overit public VIN vypis bez osobnich udaju.
