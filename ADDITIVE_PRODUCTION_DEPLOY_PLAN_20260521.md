# Additive Production Deploy Plan 2026-05-21

## Release Candidate

- Branch: `release/additive-functions-to-production-20260521`
- Base used: actual production head `20ede5ace2a013e067c07704ec153a6b2018d028`
- Candidate head at plan creation: `8581a93940e7bf0dd4621258b05eb76f60a43fe4`
- Production deploy status: not deployed.

## What Will Be Deployed

- Additive service map backend:
  - standalone `/api/v1/service-map/*` API
  - optional authenticated `/api/v1/system/maps-config`
  - new service map tables
- Additive service work-order item/CSV backend:
  - `/api/v1/services/workspace/.../items`
  - CSV preview and confirmed import endpoints
  - intake-to-work-order conversion endpoint
  - new work-order item/import tables
- Tests and documentation.

## What Will Not Be Deployed

- User invoice backend/frontend.
- Service invoice dashboard frontend.
- `web/service-shell.js`, `web/service-shell.css`.
- Staging `web/index.html` and `web/user-app-next.js` changes.
- Import/seed scripts.
- `.env`, `.env.example`, Cloudflare/systemd/nginx config.
- Any automatic service-map data import.
- Any production data rewrite.

## Migrations

Run only after DB backup and explicit production approval:

```bash
cd /opt/toozhub2/app
alembic upgrade head
```

Included migration verdicts:

- `20260516_0041_staging_revision_compat.py`: no-op, safe.
- `20260519_0041_service_work_order_items.py`: creates new table/indexes only, safe.
- `20260520_0042_service_work_order_csv_imports.py`: creates new table/indexes and nullable `note` on the new item table only, safe.
- `20260520_0043_service_map_locations.py`: creates new service-map tables/indexes only, safe.

## Pre-Deploy Production Checklist

```bash
cd /opt/toozhub2/app
git status --short
git branch --show-current
git rev-parse HEAD
curl -fsS http://127.0.0.1:8000/health
```

Continue only if production state is approved and clean or explicitly documented.

## DB Backup

Use SQLite online backup, not raw `cp`:

```bash
mkdir -p /opt/toozhub2/backups/pre_additive_release_20260521
DB_SRC=/opt/toozhub2/data/vehicles.db
DB_BACKUP=/opt/toozhub2/backups/pre_additive_release_20260521/vehicles_prod_pre_additive_release_$(date -u +%Y%m%dT%H%M%SZ).db
sqlite3 "$DB_SRC" ".backup '$DB_BACKUP'"
sqlite3 "$DB_BACKUP" "PRAGMA integrity_check;"
```

Expected integrity result: `ok`.

## Git Deploy Command

Only after approval:

```bash
cd /opt/toozhub2/app
git fetch origin --tags
git checkout -B production/additive-functions-20260521 origin/release/additive-functions-to-production-20260521
git rev-parse HEAD
```

Expected candidate SHA: the pushed head of `release/additive-functions-to-production-20260521`.

## Migration Command

```bash
cd /opt/toozhub2/app
alembic current
alembic upgrade head
alembic current
```

## Restart Command

```bash
systemctl restart toozhub2.service
systemctl status toozhub2.service --no-pager -l | head -80
curl -fsS http://127.0.0.1:8000/health
```

## Smoke Test

Backend/API:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS "http://127.0.0.1:8000/api/v1/service-map/search?lat=49.75&lng=16.47&radius_km=10&limit=5"
```

Authenticated manual smoke after deploy:

- Existing user login still works.
- Existing dashboard loads.
- Vehicles load.
- Documents load.
- Reminders load.
- Services tab remains visible.
- Service workspace existing pages still load.
- Service-map search returns an empty safe result if no data is imported.
- Work-order CSV preview does not write rows.
- CSV import writes only after explicit service user confirmation.
- User invoices remain absent/disabled.

## Rollback Procedure

If deploy or health fails:

```bash
cd /opt/toozhub2/app
git checkout -B production/rollback-prod-trial-countdown-ui-20260521 prod-trial-countdown-ui-20260521
systemctl restart toozhub2.service
curl -fsS http://127.0.0.1:8000/health
```

## DB Restore

If migrations were applied and rollback must remove their DB effects, restore from the verified backup:

```bash
systemctl stop toozhub2.service
sqlite3 /opt/toozhub2/backups/pre_additive_release_20260521/<BACKUP_FILE>.db "PRAGMA integrity_check;"
cp /opt/toozhub2/backups/pre_additive_release_20260521/<BACKUP_FILE>.db /opt/toozhub2/data/vehicles.db
systemctl start toozhub2.service
curl -fsS http://127.0.0.1:8000/health
```

The backup file must be the one created immediately before deploy and must have returned `ok`.

## Old Function Verification

After rollback or deploy, verify:

- Login/register/email verification.
- License trial countdown modal.
- User services tab.
- Admin archive UI.
- Vehicle list/detail.
- Documents/reminders/service records.

## Production Approval Gate

Do not deploy this release to production until the operator explicitly approves:

- final release branch SHA,
- DB backup path,
- migration command,
- restart window,
- smoke test owner,
- rollback owner.
