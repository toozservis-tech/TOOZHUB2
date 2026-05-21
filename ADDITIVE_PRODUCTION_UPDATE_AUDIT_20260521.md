# Additive Production Update Audit 2026-05-21

## Scope

- Repository: `toozservis-tech/TOOZHUB2`
- Staging source: `freeze/staging-current-ui-20260520` (`ccd384acfbc8229a821bb6e31c5548170e7fcb5e`)
- Requested legacy production tag: `prod-frontend-ui-20260521` (`3fe02d581c0701f52a7b8e5cdfc5b4d66e94668e`)
- Actual production baseline preserved for this release candidate after final production read-only check: `apprepo/fix/backend-sanity-gate-ci-20260521` (`04882c747586bd4751e71de31db190abf6809fdd`)
- Release candidate branch: `release/additive-functions-to-production-20260521`

The requested production tag is older than the current production working state. During final read-only verification the production tree was on `fix/backend-sanity-gate-ci-20260521` at `04882c747586bd4751e71de31db190abf6809fdd`, so the candidate was rebased onto that exact production head to avoid overwriting the currently deployed backend sanity fix and admin/archive fixes.

## Staging Diff Summary

Command audited:

```bash
git diff --name-status prod-frontend-ui-20260521..freeze/staging-current-ui-20260520
```

The staging diff includes service map code, service work-order item/CSV code, invoice frontend/backend experiments, service shell changes, import scripts, migrations, tests, and documentation. Only additive service map and service work-order item/CSV pieces were selected.

## Functional Packages

### 1. Service map / servisy v okoli

- Files included:
  - `src/modules/vehicle_hub/routers_v1/service_map.py`
  - `src/modules/vehicle_hub/service_map/*`
  - `src/modules/vehicle_hub/models.py`
  - `src/modules/vehicle_hub/schema_management.py`
  - `src/modules/vehicle_hub/routers_v1/__init__.py`
  - `src/modules/vehicle_hub/routers_v1/capabilities.py`
  - `src/core/config.py`
  - `alembic/versions/20260520_0043_service_map_locations.py`
  - `tests/api/test_service_map.py`
  - `docs/SERVICE_MAP_IMPORT.md`
- Purpose: add standalone service-location catalog API and optional map tile config.
- Classification: `ADD` plus `MODIFY_SAFE` router/schema/config wiring.
- Requires migration: yes, creates only new service map tables.
- Requires env variables: no required values. Optional `MAP_PROVIDER`, `MAP_TILE_URL`, `MAPY_COM_API_KEY`, `GOOGLE_MAPS_API_KEY`.
- Changes existing behavior: no existing service workflow is modified.
- Writes to DB: search/detail are read-only; authenticated report/claim endpoints create new service-map report/claim rows only.
- Auto-activation after deploy: API routes become available, but no production data is imported automatically.
- Recommendation: `INCLUDE`.

### 2. Service work order CSV import

- Files included:
  - `src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py`
  - `src/modules/vehicle_hub/models.py`
  - `src/modules/vehicle_hub/schema_management.py`
  - `src/modules/vehicle_hub/routers_v1/__init__.py`
  - `alembic/versions/20260519_0041_service_work_order_items.py`
  - `alembic/versions/20260520_0042_service_work_order_csv_imports.py`
  - `tests/api/test_service_work_order_items.py`
- Purpose: add items, totals, CSV preview/import, and intake-to-work-order conversion for service workspace.
- Classification: `ADD` plus `MODIFY_SAFE` router/schema wiring.
- Requires migration: yes, creates new tables and adds nullable `note` column only if the new item table exists.
- Requires env variables: no.
- Changes existing behavior: no existing service invoice/user vehicle behavior is modified.
- Writes to DB: only when an authenticated service account explicitly creates/imports items or converts an intake.
- Auto-activation after deploy: endpoints become available to service workspace roles.
- Recommendation: `INCLUDE`.

### 3. Service invoice dashboard frontend

- Files excluded:
  - `web/service-shell-invoices-dashboard.css`
  - `web/service-shell-invoices-dashboard.js`
  - `web/service-shell.js`
  - `web/service-shell.css`
- Purpose: service invoice dashboard UI.
- Classification: `MODIFY_RISKY`, because it depends on `web/service-shell.js` changes and affects existing service shell behavior.
- Requires migration: no new migration selected.
- Requires env variables: no.
- Changes existing behavior: yes, service shell invoice UI behavior changes.
- Writes to DB: via existing invoice APIs if activated.
- Auto-activation after deploy: yes if service shell assets are shipped.
- Recommendation: `EXCLUDE`.

### 4. Service shell doplneni

- Files excluded:
  - `web/service-shell.js`
  - `web/service-shell.css`
  - `tests/e2e/service-shell-fallback.helpers.ts`
  - `tests/e2e/service-shell-work-order-flow.spec.ts`
- Purpose: staging service shell UI integration.
- Classification: `MODIFY_RISKY`.
- Requires migration: no.
- Requires env variables: no.
- Changes existing behavior: yes, directly changes the existing service shell.
- Writes to DB: indirectly if activated.
- Auto-activation after deploy: yes.
- Recommendation: `EXCLUDE` for this release candidate.

### 5. User invoice backend

- Files excluded:
  - `src/modules/vehicle_hub/routers_v1/user_invoices.py`
  - user-invoice additions inside `src/modules/vehicle_hub/routers_v1/__init__.py`
  - user invoice additions inside `src/modules/vehicle_hub/routers_v1/vehicles.py`
  - invoice behavior changes inside `src/modules/vehicle_hub/routers_v1/service_invoices.py`
- Purpose: user invoice workflow.
- Classification: `MODIFY_RISKY`.
- Requires migration: not selected.
- Requires env variables: no.
- Changes existing behavior: yes, invoice ownership/PDF/listing behavior changes.
- Writes to DB: yes for invoice workflow/audit.
- Auto-activation after deploy: yes if routes/assets are shipped.
- Recommendation: `EXCLUDE`. User invoices remain a separate accounting release.

### 6. User invoice frontend

- Files excluded:
  - `web/user-invoice-settings.js`
  - `web/user-invoices-dashboard.js`
  - `web/user-invoices-shell-adapter.js`
  - `web/user-invoices-workflow.js`
  - invoice-related `web/index.html` changes
  - invoice-related `web/user-app-next.js` changes
- Purpose: user invoice UI.
- Classification: `MODIFY_RISKY`.
- Requires migration: backend workflow not approved.
- Requires env variables: no.
- Changes existing behavior: yes, activates unfinished invoice surfaces.
- Writes to DB: indirectly through invoice APIs.
- Auto-activation after deploy: yes if scripts are included.
- Recommendation: `EXCLUDE`.

### 7. Public/user UI already deployed

- Files excluded from this backend candidate:
  - `web/index.html`
  - `web/user-app-next.js`
- Purpose: frontend-only production UI release already deployed separately.
- Classification: already production baseline, no new change needed here.
- Requires migration: no.
- Requires env variables: no.
- Changes existing behavior: no change in this candidate.
- Writes to DB: no.
- Auto-activation after deploy: no new activation.
- Recommendation: `EXCLUDE`.

### 8. Security/config changes

- Files included:
  - `src/core/config.py` optional map env keys only.
  - `src/modules/vehicle_hub/routers_v1/capabilities.py` authenticated `/system/maps-config` only.
- Files excluded:
  - `.env.example`
  - `src/core/security_middleware.py`
- Classification: selected config change is `MODIFY_SAFE`; excluded security middleware is `MODIFY_RISKY` until separately reviewed.
- Requires migration: no.
- Requires env variables: no required variables.
- Changes existing behavior: no existing behavior changes; optional map config endpoint is additive.
- Writes to DB: no.
- Auto-activation after deploy: authenticated map config route becomes available.
- Recommendation: `INCLUDE` selected optional map config only.

### 9. Alembic migrations

- Included migrations:
  - `20260516_0041_staging_revision_compat.py`
  - `20260519_0041_service_work_order_items.py`
  - `20260520_0042_service_work_order_csv_imports.py`
  - `20260520_0043_service_map_locations.py`
- Classification: `ADD`.
- Recommendation: `INCLUDE`.

### 10. Scripts/importy

- Files excluded:
  - `scripts/import_service_map_osm_cz.py`
  - `scripts/seed_service_map_staging.py`
- Purpose: service map data import/seed.
- Classification: `MODIFY_RISKY` for production operations because these can write/import data.
- Requires migration: service map tables if manually run.
- Requires env variables: no.
- Changes existing behavior: no, but can write data when executed.
- Writes to DB: yes if run.
- Auto-activation after deploy: no.
- Recommendation: `EXCLUDE`. No production import without manual approval.

### 11. Testy

- Files included:
  - `tests/api/test_service_map.py`
  - `tests/api/test_service_work_order_items.py`
- Purpose: validate selected additive backend packages.
- Classification: `ADD`.
- Recommendation: `INCLUDE`.

### 12. Dokumentace

- Files included:
  - `docs/SERVICE_MAP_IMPORT.md`
  - `ADDITIVE_PRODUCTION_UPDATE_AUDIT_20260521.md`
  - `ADDITIVE_PRODUCTION_DEPLOY_PLAN_20260521.md`
- Files excluded:
  - staging-only implementation/test reports unless separately needed.
- Classification: `ADD`.
- Recommendation: `INCLUDE`.

## Migration Audit

### `20260516_0041_staging_revision_compat.py`

- Creates: nothing.
- Modifies: nothing.
- Drop: no upgrade drop.
- Alter existing column: no.
- Rename: no.
- Data writes: no.
- Additive-only: yes, compatibility no-op.
- Downgrade: no-op.
- Production verdict: safe.

### `20260519_0041_service_work_order_items.py`

- Creates: `service_work_order_items` and indexes.
- Modifies: no existing tables.
- Drop: upgrade no; downgrade drops the new table only.
- Alter existing column: no.
- Rename: no.
- Data writes: no.
- Additive-only: yes.
- Downgrade: drops only the new table.
- Production verdict: safe. Rollback should restore DB backup instead of relying on downgrade if data was created.

### `20260520_0042_service_work_order_csv_imports.py`

- Creates: `service_work_order_csv_imports` and indexes.
- Modifies: adds nullable `note` column to `service_work_order_items` only if that new table exists.
- Drop: upgrade no; downgrade drops the new CSV import table only.
- Alter existing column: no.
- Rename: no.
- Data writes: no.
- Additive-only: yes.
- Downgrade: drops only the new CSV import table and intentionally keeps nullable note column.
- Production verdict: safe.

### `20260520_0043_service_map_locations.py`

- Creates: `service_locations`, `service_location_sources`, `service_location_claims`, `service_location_reports`, indexes, and one unique index on source identity.
- Modifies: no existing tables.
- Drop: upgrade no; downgrade drops only the new service-map tables.
- Alter existing column: no.
- Rename: no.
- Data writes: no.
- Additive-only: yes.
- Downgrade: drops only new tables.
- Production verdict: safe. Rollback should restore DB backup if service-map data has been created.

## Static Checks

- `python3 -m compileall src`: PASS.
- `pytest tests/api/test_license*.py -q`: PASS, `34 passed`.
- `pytest tests/api/test_service_map.py -q`: PASS, `15 passed`.
- `pytest tests/api/test_service_work_order_items.py -q`: PASS, `14 passed`.
- Excluded diff guard: `OK_EXCLUDED_DIFF`.

## License and Trial Changes

Follow-up audit document: `LICENSE_TRIAL_RELEASE_AUDIT_20260521.md`.

What was found:

- `8598eda` (`Start 30 day premium trial on first user login`) was already included through the production baseline ancestry.
- `04882c7` (`Fix backend sanity gate for CI and stale audit-trail tests.`) was already the release candidate base.
- `5478147` (`Refresh services tab visibility after license load`) was missing and was added by cherry-pick.
- `20ede5a` (`Show premium trial countdown in license modal`) was missing and was added by cherry-pick.

Newly added files/changes:

- `web/index.html` only.

No license/trial migration was added. The existing backend trial logic remains the production-origin implementation:

- first login can create a 30-day Premium trial for a new user,
- expired trial evaluates as Free without deleting data,
- paid upgrade clears expired trial state,
- existing paid/service accounts are not converted.

Runtime verification on staging:

- `/api/me`: PASS for user and service.
- `/api/v1/license/status`: PASS for lifetime, service_free, free, and basic users.
- `/api/v1/system/capabilities`: PASS.
- service map and work-order CSV smoke: PASS.

Risks:

- The added license/trial changes are UI visibility/countdown only.
- Comgate recurring state, prices, paid plans, and user invoices were not changed.
- User invoice files remain excluded.

## Decision

Included:

- Service map backend/API, optional authenticated map config, additive DB tables.
- Service work-order item and CSV backend/API, additive DB tables.
- Production-origin trial activation backend already in baseline.
- Production-origin services tab visibility and trial countdown UI.
- Targeted API tests and service map import documentation.

Excluded:

- User invoices frontend/backend.
- Service invoice dashboard frontend.
- `web/service-shell.js` and `web/service-shell.css`.
- `web/index.html` and `web/user-app-next.js` staging changes.
- Data import scripts.
- Security middleware changes.
- Existing invoice/vehicle behavior changes.

Feature-flagged:

- No runtime feature flag was needed because no staging UI was shipped. Service map data remains empty unless imported manually later.

Verdict: candidate is additive-only from a code and migration perspective.
