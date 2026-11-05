# Admin incident workflow (2026-11-05)

This is additive to SecurityAccessLog. It does not delete/relabel historical failures, replay a customer request, grant entitlements, change ownership, send email or contact an AI service. An administrator explicitly opens a support case from a problem event.

## API

All routes start `/admin-api/control-center/incidents` and use the existing current administrative assurance check. Cookie-only access is not supported; authenticated browser writes also check same origin or an explicitly configured allowed origin, never a wildcard or an untrusted forwarded-host header. Responses are no-store.

- GET collection: status=active (open + in_progress), all, open, in_progress, resolved, dismissed; search; limit 1–100; offset. Returns total, items, summary.
- POST `/from-event/{event_id}`: idempotently opens the event's existing case, including if closed. A different event for the same actor, endpoint, resource and HTTP result attaches only to an active case. A recurrence after closure creates a new case. Races return 409 with no partial link.
- GET `/{id}`: actor, title, state/version, source event, linked_event_count/recurrence_count, diagnosis, checks, latest 200 events and 200 history entries with totals/truncation flags.
- GET `/{id}/history` and `/{id}/events`: limit 1–200; offset. Older retained evidence remains accessible.
- POST `/{id}/transition`: `{status,note,expected_version,client_id}`. UUID client_id is idempotent per administrator/case. Version check is atomic. Resolve, dismiss and reopen require a reason. Closed cases reopen to open only; another active matching case must be handled first.
- POST `/{id}/notes`: `{note,expected_version,client_id}`; 3–2000 characters. No edit or delete operation.
- GET `/{id}/check`: SELECT-only account, role, license/current active reward, related transfer/referral context. Does not reconcile payments, create a missing license, award referrals or fix the case automatically. Suggested actions are allowlisted product targets, never arbitrary URLs/commands.
- GET `/{id}/diagnostic`: `{text,redacted:true,format:"text/plain"}` for preview and explicit manual sharing. Includes case/event IDs, timestamp, validated platform/version/build/OS, normalized route and HTTP result. Up to ten steps in the preceding fifteen minutes: allowlisted app step codes distinguished from server-recorded outcomes. Excludes actor identity, email, IP, VIN/resource IDs, headers, bodies, credentials, free-form reasons, comments, payment data and arbitrary user agents.

`known_subscription_restriction` requires an explicit known restriction code saved with the 403. Current lack of Premium is only `current_restriction_possible`, never proof of the historical cause. Other 403s remain `access_denied_unexplained`. A resolved case is an administrator's recorded conclusion, not execution of a repair.

## Preservation and erasure

Normal case actions append history and a DeveloperActionAuditLog entry in the same transaction. Historical error counts and unresolved case counts are separate. Explicit account erasure follows the already-existing deletion scope of SecurityAccessLog: cases about the erased account are removed before those logs. An erased administrator's authorship and free-text note are anonymized in another account's surviving case, preserving the event, decision and timestamp. There is no incident API for erasure.

## Migration / rollout

Alembic head `20261105_0027` after `20261105_0026` invokes `scripts.migrate_admin_incidents.migrate_connection`. It creates three additive tables with checkfirst; repeated migration preserves cases/events/history. Until migrated, case routes return actionable 503 while original activity routes continue. The actual pre-deploy entry point `python -m scripts.migrate_mobile_release` invokes the transfer/reinvite migrations and the new incident migration, each repeatable. The packaged Docker COPY layout is tested in two independent fresh Python processes against an existing database. No production migration/deployment was performed by this task.

Backend local verification: 43 tests passed on Python 3.12.14, including real SQLite concurrency (two administrators; recurrence versus closure), actual authenticated role/assurance checks, Origin/CSRF, idempotency, reopen, >200 notes pagination, hostile export context, SELECT-only diagnosis, Free/Basic analytics403 versus Premium/service/admin200, original activity regressions, and complete account erasure with foreign keys enabled.

Command:

```sh
PYTHONPATH=.:tests/security /Users/toozservis/Developer/toozhub-parity-runtime-20261027/venv/bin/python -m pytest tests/security/test_admin_incidents.py tests/api/test_admin_incident_race.py tests/security/test_access_history.py tests/security/test_account_erasure_graph.py tests/api/test_mobile_release_migration.py -q --disable-warnings
```

Shared UI fixture: `tests/web/admin_incidents_fixture_20261105.py`, loopback only on 18917. Dedicated SQLite at `../admin-incidents-qa-20261105/shared.sqlite`; synthetic groups ios/web/android. Explicit resume preserves evidence and JWTs. It mounts real admin and analytics routes with fixture-only authentication and empty synthetic dashboard records. `/qa/plan` changes only a fixture customer's plan. `/qa/requests` and `/qa/request-counts` record method/path/result per fixture group, never tokens/bodies. This is not production authentication or production data evidence.
