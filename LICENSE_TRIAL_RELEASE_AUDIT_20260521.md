# License Trial Release Audit 2026-05-21

## Baselines

- Production baseline: `04882c747586bd4751e71de31db190abf6809fdd`
- Release candidate before this audit: `a1efab7fe839294272fa7bb79054a8084c1d82ef`
- Staging source: `freeze/staging-current-ui-20260520`
- Release branch: `release/additive-functions-to-production-20260521`

Production was not modified and was not restarted during this audit.

## Search Results

Relevant commits found:

- `8598eda` - `Start 30 day premium trial on first user login`
- `5478147` - `Refresh services tab visibility after license load`
- `20ede5a` - `Show premium trial countdown in license modal`
- `04882c7` - `Fix backend sanity gate for CI and stale audit-trail tests.`
- `019e80b` - older service license flow/admin invoice visibility baseline

Ancestor check against the release candidate before this update:

- `8598eda`: already included.
- `04882c7`: already included.
- `5478147`: missing.
- `20ede5a`: missing.

The missing commits are production hotfix commits from the earlier license/trial work, not staging-only invoice work.

## Compared Files

Commands audited:

```bash
git diff --name-status 04882c747586bd4751e71de31db190abf6809fdd..release/additive-functions-to-production-20260521 -- src web tests alembic docs
git diff --name-status release/additive-functions-to-production-20260521..freeze/staging-current-ui-20260520 -- src web tests alembic docs
git diff --name-status 04882c747586bd4751e71de31db190abf6809fdd..freeze/staging-current-ui-20260520 -- src web tests alembic docs
```

Relevant files reviewed:

- `src/modules/vehicle_hub/routers_v1/license_status.py`
- `src/modules/vehicle_hub/routers_v1/capabilities.py`
- `src/modules/vehicle_hub/schema_management.py`
- `src/modules/vehicle_hub/models.py`
- `src/modules/licensing/service.py`
- `src/server/main_helpers.py`
- `src/server/admin_api.py`
- `src/core/config.py`
- `web/index.html`
- `web/user-app-next.js`
- `tests/api/test_license_comgate_utils.py`
- `tests/api/test_license_service_free_quotas.py`

## Already In Release Candidate

### 30-day premium trial backend

Source: production commit `8598eda`.

Files already present through the production baseline ancestry:

- `src/modules/vehicle_hub/routers_v1/license_status.py`
- `src/modules/licensing/service.py`
- `tests/api/test_license_service_free_quotas.py`

Behavior:

- First user login can activate an initial 30-day Premium trial.
- Expired trial is evaluated as Free without deleting data.
- Paid upgrade clears expired trial `valid_to`.
- Existing paid accounts are not converted to trial.

### Backend sanity gate

Source: production commit `04882c7`.

Already present as the release candidate base. No extra transfer needed.

## Newly Added To Release Candidate

### Services tab visibility refresh

Source: production commit `5478147`.

Included by cherry-pick:

- `web/index.html`

Reason:

- The UI refreshes services tab visibility after license state loads.
- This is license gating UI behavior, not invoice UI.

### Premium trial countdown in license modal

Source: production commit `20ede5a`.

Included by cherry-pick:

- `web/index.html`

Reason:

- Shows the trial banner/countdown from the license status payload.
- Makes 30-day trial state visible to the user.
- Does not alter backend plans, pricing, Comgate, or DB data.

## Intentionally Not Added

- Staging changes in `src/modules/vehicle_hub/routers_v1/user_invoices.py`.
- Staging changes in `src/modules/vehicle_hub/routers_v1/service_invoices.py`.
- Staging changes in `src/modules/vehicle_hub/routers_v1/vehicles.py`.
- Staging changes in `src/server/admin_api.py`, `src/server/main_helpers.py`, and `src/server/routers/user_auth.py`.
- Staging invoice frontend files.
- `web/service-shell.js` and `web/service-shell.css`.
- Import scripts.

Reason:

- These are invoice, staging-only, or broader behavior changes.
- They are not required for trial/license preservation.
- They could activate unfinished invoices or modify existing workflows.

## Migration Review

No new license/trial migration was added in this update.

Existing license/Comgate migrations were reviewed by grep. They are already part of the production baseline history and were not changed by this candidate. The additive release migrations remain:

- `20260516_0041_staging_revision_compat.py`
- `20260519_0041_service_work_order_items.py`
- `20260520_0042_service_work_order_csv_imports.py`
- `20260520_0043_service_map_locations.py`

No migration in this update:

- activates trial for all existing users,
- changes paid/service accounts,
- rewrites Comgate recurring state,
- changes prices or plans.

## Test Results

- `python3 -m compileall src`: PASS
- `pytest tests/api/test_license*.py -q`: PASS, `34 passed`
- `pytest tests/api/test_trial*.py -q`: no matching files
- `pytest tests/api/test_capabilities*.py -q`: no matching files
- `pytest tests/api/test_service_map.py -q`: PASS, `15 passed`
- `pytest tests/api/test_service_work_order_items.py -q`: PASS, `14 passed`

Trial coverage exists in `tests/api/test_license_service_free_quotas.py`:

- first login activates user premium trial,
- expired trial behaves as Free without data loss,
- paid upgrade clears expired trial,
- Free user quota remains enforced,
- service Free quotas remain separate from user plan behavior.

## Staging Runtime Result

Backup:

- `/opt/toozhub2-staging/backups/pre_license_trial_release_20260521/vehicles_staging_pre_license_trial_release_20260521_20260521T172935Z.db`

Integrity:

- `PRAGMA integrity_check`: `ok`

Alembic:

- before: `20260520_0043 (head)`
- after `alembic upgrade head`: `20260520_0043 (head)`

Restart:

- restarted only `toozhub2-staging.service`
- production service was not restarted

Runtime smoke:

- `/health`: PASS
- `/api/me` user: PASS
- `/api/me` service: PASS
- `/api/v1/license/status` lifetime user: PASS, full features remain enabled
- `/api/v1/license/status` service_free: PASS, service plan remains separate
- `/api/v1/license/status` free user: PASS, remains Free
- `/api/v1/license/status` basic user: PASS, remains Basic
- `/api/v1/system/capabilities`: PASS
- service map search: PASS
- service work-order CSV preview/import: PASS

## Risk Assessment

Risk remains low because:

- The newly added commits are production-origin UI fixes, not staging invoice changes.
- Backend trial activation was already present.
- No Comgate flow was changed.
- No license/trial migration was added.
- Existing paid plans were verified at runtime.

Rollback:

- Revert the two UI commits if the license modal display misbehaves:
  - `Refresh services tab visibility after license load`
  - `Show premium trial countdown in license modal`
- For DB rollback, use the pre-deploy production DB backup from the deploy plan.

## Verdict

The release candidate now preserves the prior license/trial production work and remains additive-only with user invoices excluded.
