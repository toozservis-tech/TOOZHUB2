# Staging current state 2026-05-20

Generated from `/opt/toozhub2-staging/app` on 2026-05-21 UTC.

## Git

- Branch: `freeze/staging-current-ui-20260520`
- HEAD: `f6f28e21061e68b6826afe210c0eaefe8aeebeb7`
- Last commit: `f6f28e2 Freeze current staging UI state`
- Tag created: `staging-current-ui-20260520`

## git status --short

```text
clean after freeze commit and before this audit document was added
```

## Service status

```text
● toozhub2-staging.service - TooZ Hub 2 API Server (staging)
     Loaded: loaded (/etc/systemd/system/toozhub2-staging.service; enabled; vendor preset: enabled)
    Drop-In: /etc/systemd/system/toozhub2-staging.service.d
             └─10-supplementary-adm.conf
     Active: active (running) since Thu 2026-05-21 06:11:13 UTC
   Main PID: 2228570 (python)
      Tasks: 3
     Memory: 204.5M
     CGroup: /system.slice/toozhub2-staging.service
             └─2228570 /opt/toozhub2-staging/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8010
```

## Health

```json
{"status":"ok","project":"Správa vozidel","service":"Správa vozidel API","version":"2.2.0","version_name":"Správa vozidel 2.2.0","build_date":"2026-05-21","update_info":"Kompletní redesign UI + zavedení verzování","environment":"staging","timestamp":"2026-05-21T06:30:23.118077"}
```

## Changed / important UI files in freeze commit

```text
web/assets/landing/sprava-vozidel-logo-mark.svg
web/index.html
web/service-shell-invoices-dashboard.js
web/service-shell.js
web/user-app-next.css
web/user-app-next.js
web/user-invoices-dashboard.js
web/user-invoices-shell-adapter.js
src/modules/vehicle_hub/routers_v1/__init__.py
src/modules/vehicle_hub/routers_v1/capabilities.py
src/modules/vehicle_hub/routers_v1/service_invoices.py
src/modules/vehicle_hub/routers_v1/service_map.py
src/modules/vehicle_hub/routers_v1/services.py
src/modules/vehicle_hub/routers_v1/user_invoices.py
src/modules/vehicle_hub/routers_v1/vehicles.py
src/server/admin_service_map.py
src/server/bootstrap.py
```

## Database backup

- Source: `/opt/toozhub2-staging/data/vehicles_staging.db`
- Backup: `/opt/toozhub2-staging/backups/vehicles_staging_current_ui_20260520_20260521T063004Z.db`
- Backup method: SQLite online backup via `sqlite3 .backup`
- Integrity check on backup: `ok`

## Known functional areas from this audit

- `toozhub2-staging.service` is active and listening on `127.0.0.1:8010`.
- `/health` returns `status: ok` with `environment: staging`.
- Current staging code state is frozen in branch `freeze/staging-current-ui-20260520`.
- Current staging database backup passed SQLite integrity check.

## Known unfinished / unverified areas

- No functional UI smoke test was run as part of this freeze.
- Staging service was not restarted after the freeze commit, so the running process may not reflect every committed file until the next approved restart.
- Production parity is not established; the parity report lists many code and UI differences.
- Service map, invoice dashboard, and related user UI changes are captured as the reference state, not approved for production.

## Freeze note

This state is the reference point for further staging development. New UI work must branch from, compare against, or explicitly supersede this frozen staging state.
