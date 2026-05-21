# PRODUCTION REGRESSION INCIDENT — 2026-05-21

**Status:** PARTIAL RESTORE — hotfix applied, regression audit incomplete  
**Goal:** Restore MDČR VIN data, vehicle image by VIN, and other regressed functions.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 2026-05-21 17:29 | Incident opened — MDČR VIN + vehicle image reported broken |
| 2026-05-21 17:30 | Read-only production audit completed |
| 2026-05-21 17:32 | Minimal hotfix applied (placeholder SVG + alembic 0041 compat) |
| 2026-05-21 17:32 | DB backup + tag `prod-before-mdcr-vin-image-hotfix-20260521` |

---

## Current Production State

| Field | Value |
|-------|-------|
| Branch | `fix/backend-sanity-gate-ci-20260521` |
| HEAD | `04882c747586bd4751e71de31db190abf6809fdd` |
| Health | OK (`/health` 200, v2.2.0) |
| Alembic | `20260516_0041 (head)` — after hotfix |
| Service | `toozhub2.service` active since 2026-05-21 15:01 UTC |
| Release deploy | **BLOCKED** — no further deploy until regression audit |

---

## What's Broken (Reported)

1. MDČR vehicle data loading by VIN
2. Vehicle image/photo loading by VIN
3. Possibly other functions after update/migration

---

## Verified

### Git / runtime
- Production on `fix/backend-sanity-gate-ci-20260521` @ `04882c7`
- No MDČR/VIN backend code diff vs `prod-current-stable-20260520`
- Changes since stable: licensing trial, admin archive, `web/index.html`, new `web/user-app-next.js`
- `toozhub2.service` running, health OK

### Env / config (secrets redacted)
- `DATAOVO_API_KEY` — present, runtime loads OK
- `DATAOVO_API_BASE_URL` — `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`
- `VEHICLE_IMAGE_PROVIDER=serpapi`, `VEHICLE_IMAGE_API_KEY` — present
- MDČR client reads correct env names via `config.py` aliases

### MDČR API (backend)
- Direct call to dataovozidlech.cz: HTTPS OK, API responds (401 with bad key, Status 3 for unknown VIN)
- Outbound TLS from production venv: OK
- **Backend MDČR client is functional**

### Catalog image (backend)
- SerpAPI preview: `ok: True`, provider `serpapi`, generates `/api/v1/vehicles/catalog-images/{id}/file`
- Catalog images stored under `data/catalog_vehicle_images/`
- Protected endpoint requires auth (401 without token — expected)

### Static assets (before hotfix)
- `/web/assets/vehicle-placeholder.svg` → **404** (referenced by backend + frontend fallback)
- After hotfix → **200**

### Alembic (before hotfix)
- DB stamped `20260516_0041`, code head `20260516_0040` → `alembic current` FAILED
- After hotfix (compat migration file added) → `20260516_0041 (head)` OK
- No new migration run on production DB

### DB
- Path: `/opt/toozhub2/data/vehicles.db` (symlink → volume)
- `PRAGMA integrity_check`: **ok**
- Backup: `/opt/toozhub2/data/backups/vehicles.db.pre-mdcr-vin-image-hotfix-20260521T173201Z`

### License / VIN decode gating
- `assert_feature(db, tenant_id, "vin_decode")` blocks decode for FREE plan
- Production DB: **97 free** tenants with `vin_decode_enabled=0`, **7 lifetime**, **8 premium/trial** with decode enabled
- Same FREE gating existed at `prod-current-stable-20260520` — **not a new code regression**
- New 30-day trial on first login gives premium + vin_decode (commit `8598eda`)

### Frontend
- `user-app-next.js` delegates VIN/add-vehicle to legacy handlers (`openAddVehicleModal`, `refreshExistingVehicleFromVin`)
- UI gates VIN by `vin_decode_enabled` / plan rank

---

## Root Causes

### MDČR VIN data
**Primary:** For majority of users (FREE plan), VIN decode is **license-gated** — returns error via `assert_feature`, not MDČR API failure.  
**Secondary:** MDČR API itself works when license allows; config/env correct.  
**Not the cause:** Backend code regression (no diff vs stable), missing API key, TLS failure.

### Vehicle image by VIN
**Primary:** Missing static asset `/web/assets/vehicle-placeholder.svg` (404) — breaks fallback UI when catalog search fails or during loading states.  
**Secondary:** Catalog images served via auth-protected endpoint — frontend must use `hydrateAuthorizedImageUrl` (already implemented).  
**Not the cause:** SerpAPI provider (works), missing API key.

---

## Hotfix Applied (minimal, no .env change, no new DB migration run)

| File | Change |
|------|--------|
| `web/assets/vehicle-placeholder.svg` | Restored from commit `714497c` |
| `alembic/versions/20260516_0041_staging_revision_compat.py` | Added no-op compat marker (DB already at 0041) |

**Backend NOT restarted** — static file served immediately; alembic file is tooling-only.

---

## Rollback Plan

```bash
cd /opt/toozhub2/app
git checkout prod-before-mdcr-vin-image-hotfix-20260521
# or restore DB from backup if needed:
# cp /opt/toozhub2/data/backups/vehicles.db.pre-mdcr-vin-image-hotfix-20260521T173201Z /opt/toozhub2/data/vehicles.db
```

---

## Regression Checklist (structural / API)

| Area | Result | Notes |
|------|--------|-------|
| `/health` | PASS | 200 |
| `/version` | PASS | 200 |
| `/api/me` no auth | PASS | 200, `authenticated:false` |
| MDČR API outbound | PASS | HTTPS + API response |
| VIN decode endpoint | PARTIAL | 401 without auth; license-gated for FREE |
| Catalog image SerpAPI | PASS | Backend generates images |
| Placeholder fallback | PASS (after hotfix) | 200 |
| Alembic current | PASS (after hotfix) | 0041 = head |
| Login | NOT FULLY TESTED | — |
| Documents/reminders/vehicles | NOT FULLY TESTED | — |
| Service endpoints | NOT FULLY TESTED | — |

---

## Test Results

- `compileall src`: OK
- `pytest test_health`: 3 passed, 1 skipped
- `pytest test_vin_decode`: 7 errors (test registration 422 — pre-existing test env issue, not hotfix)
- `pytest test_auth/vehicles`: some failures (certifi path in test client env)

---

## Tags

- `prod-before-mdcr-vin-image-hotfix-20260521` — before hotfix
- `prod-mdcr-vin-image-restored-20260521` — pending after verification

---

## Blockers

1. **Regression audit incomplete** — additive deploy remains blocked
2. **FREE users (97/107)** cannot use VIN decode by license policy — product decision, not fixed by hotfix
3. **End-to-end UI smoke** with real authenticated premium user not performed (no credentials)
4. **pytest auth/VIN tests** broken in test env (422 registration validation)

---

## Decision

**Hotfix** (not full rollback) — backend MDČR/image logic unchanged vs stable; issues were missing static asset + alembic tooling mismatch.

**Verdict: PRODUCTION STILL DEGRADED (PARTIAL)**  
- Placeholder/fallback restored  
- MDČR backend functional for licensed users  
- FREE-tier VIN decode still blocked by design  
- Full regression audit + authenticated UI verification still required for PASS
