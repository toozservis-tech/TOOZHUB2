# Servisní workspace: reality check k 2026-05-07

Tento dokument porovnává popsaný návrh servisního rozhraní s aktuálním stavem repozitáře. Slouží jako technický zdroj pravdy pro další implementaci, obchodní prezentaci a QA.

## Shrnutí

V projektu už existuje funkční základ servisního workspace:

- servisní shell na webu
- dashboard summary a fronta práce
- servisní zakázky jako `ServiceWorkOrder`
- servisní nabídky jako `ServiceQuote`
- servisní faktury jako `ServiceInvoice`
- servisní přístup k vozidlům a access request flow
- veřejná QR historie vozidla s omezením osobních údajů
- audit trail pro změny servisních záznamů a zakázek

Současně ale neplatí, že by byl celý níže popsaný návrh implementován v přesně stejné podobě. V kódu se používají jiné entity, jiné endpointy a část funkcí je zatím pouze částečná nebo chybí.

## Co je v kódu skutečně ověřeno

### Backend

- Dashboard summary a queue existují v [src/modules/vehicle_hub/routers_v1/service_dashboard.py](/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/service_dashboard.py).
- Zakázky jsou implementované jako `ServiceWorkOrder`, nikoli `ServiceOrder`.
- Nabídky ceny existují jako `ServiceQuote` a jsou provázané se zakázkou nebo servisním záznamem.
- Faktury pro servis existují jako `ServiceInvoice` v [src/modules/vehicle_hub/routers_v1/service_invoices.py](/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/service_invoices.py).
- Service access request flow existuje ve workspace a servisních routerech, nikoli jako `VehicleAccessGrant` se scope JSON v deklarované podobě.
- Audit trail existuje, ale je rozdělený do specializovaných tabulek jako `GlobalAuditLog`, `ServiceRecordAuditLog`, `ServiceWorkOrderAuditLog`, `ServiceQuoteAuditLog`.
- Veřejná historie přes QR je implementovaná a testuje minimalizaci osobních údajů.

### Frontend

- Servisní shell existuje v [web/service-shell.js](/opt/toozhub2/app/web/service-shell.js) a [web/service-shell.css](/opt/toozhub2/app/web/service-shell.css).
- Dashboard obsahuje summary, frontu práce, rychlé akce, zakázky a faktury.
- Mobilní adaptace existuje, ale aktuálně používá mobilní menu a full-screen modální flow; nejde o hotovou spodní navigaci v přesně popsané struktuře.

### Testy

- Zakázky a dashboard: [tests/api/test_service_dashboard.py](/opt/toozhub2/app/tests/api/test_service_dashboard.py)
- Přístupové žádosti: [tests/api/test_service_access_requests.py](/opt/toozhub2/app/tests/api/test_service_access_requests.py)
- Audit servisních záznamů: [tests/api/test_service_record_audit_trail.py](/opt/toozhub2/app/tests/api/test_service_record_audit_trail.py)
- Veřejná QR historie bez úniku osobních údajů: [tests/api/test_public_vehicle_history_qr.py](/opt/toozhub2/app/tests/api/test_public_vehicle_history_qr.py)
- E2E shell pro zakázky, faktury a mobile flow: `tests/e2e/service-shell-*.spec.ts`

## Hlavní rozdíly proti návrhu

### Entity a databáze

Návrh používá entity:

- `ServiceOrder`
- `ServiceRecord`
- `Invoice`
- `VehicleAccessGrant`
- `VehicleHistoryEvent`
- `AuditLog`
- `ServiceWorkspaceSettings`

Aktuální kód ale reálně používá hlavně:

- `ServiceWorkOrder`
- `ServiceRecord`
- `ServiceQuote`
- `ServiceInvoice`
- `ServiceAccessRequest`
- `VehicleServiceLink`
- `GlobalAuditLog`
- `ServiceRecordAuditLog`
- `ServiceWorkOrderAuditLog`
- `ServiceQuoteAuditLog`

V repu jsem nenašel potvrzenou implementaci tabulek `ServiceWorkspaceSettings`, `VehicleHistoryEvent` ani `VehicleAccessGrant` v podobě popsané v návrhu.

### API kontrakty

Návrh uvádí endpointy jako:

- `GET /api/v1/services/workspace/dashboard`
- `POST /api/v1/services/workspace/orders`
- `POST /api/v1/services/workspace/invoices/from-order/{id}`

Aktuální implementace používá zejména:

- `GET /api/service/dashboard/summary`
- `GET /api/service/dashboard/queue`
- `GET/POST/PUT /api/service/work-orders`
- `GET/POST/PUT /api/service/quotes`
- `GET/POST/PUT /api/service/invoices`
- `GET/POST /api/v1/services/workspace/...` pro customer/workspace/access část

To znamená, že přiložený popis dnes nelze brát jako přesnou API dokumentaci.

### Audit a immutable historie

Návrh tvrdí hash řetězení přes `immutable_hash` a `previous_hash` u více entit. V aktuálním modelu:

- `ServiceRecord` má `snapshot_hash`
- audit změn servisních záznamů se ukládá jako snapshot před/po
- veřejná QR historie má podpis tokenu a přístupový audit

Nepotvrdil jsem plnohodnotný append-only hash chain přes samostatné `VehicleHistoryEvent` záznamy v deklarované podobě.

### GDPR a veřejná historie

Tato část je částečně pravdivá už dnes:

- veřejná historie netestuje a nezobrazuje běžné osobní údaje vlastníka
- interní poznámky nejsou ve veřejném výstupu
- servisní přístup je vázaný na schválení

Naopak jsem nepotvrdil plnou implementaci granularního `scope_json` modelu ani samostatný zákaznický portál pro schválení ceny v přesně popsaném workflow.

### OCR a dokumenty

Workspace modul obsahuje ingest dokumentů a heuristický parser. Nepotvrdil jsem kompletní OCR workflow přes samostatné endpointy a ruční potvrzení ve stejné podobě, jak je popsáno v návrhu.

## Co lze bezpečně komunikovat jako implementované

- Servisní dashboard a shell existují.
- Servis umí spravovat zakázky, nabídky a faktury.
- Přístup servisu k vozidlu vyžaduje schválení vlastníka.
- Audit změn servisních záznamů a zakázek existuje.
- Veřejná QR historie je omezená tak, aby nepublikovala běžné osobní údaje.
- Existují backend i E2E testy pro klíčové servisní workflow.

## Co je potřeba komunikovat jako návrh nebo další fázi

- sjednocení názvosloví na `ServiceOrder` vs. `ServiceWorkOrder`
- samostatné servisní nastavení workspace
- granularní access scope model
- plný customer approval flow pro cenu zakázky
- plné OCR workflow se structured review
- samostatná entita veřejné servisní historie typu `VehicleHistoryEvent`
- striktní hash chain napříč všemi servisními událostmi
- mobilní spodní navigace v přesně deklarované informační architektuře

## Doporučený další krok

Nejbezpečnější další krok je sjednotit dokumentaci a kontrakty:

1. Rozhodnout, zda se budeme držet současného modelu `ServiceWorkOrder/ServiceQuote/ServiceInvoice`, nebo přejmenujeme backend na cílové názvosloví návrhu.
2. Zapsat kanonickou API specifikaci podle skutečně existujících route.
3. Teprve potom doplnit chybějící části návrhu, hlavně settings, granular access scope a structured history event model.
