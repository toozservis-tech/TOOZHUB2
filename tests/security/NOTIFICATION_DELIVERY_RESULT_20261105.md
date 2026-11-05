# Backend notification delivery result — 2026-11-05

Scope: isolated branch codex/push-admin-delivery-20261105, baseline b55a5fe2822fdf9dd1e955748d55f0eac275f8da. No production writes, provider sends, deploys or real recipient messages. Source pin and artifact hashes are outside repo in ../evidence/source-index.json after commit.

## Verified backend scenarios

- 63 security/API tests +30 existing admin-operation subtests PASS in42.13s: source-scoped history; read≠dismiss≠ack; repeated UUID/conflicts; other account/role/demo/CSRF denial; encrypted devices and token takeover; logout/session version/expiry; retry/lease/dedupe; rollout cursor; archived snapshots; scheduled audience; provider HTTP mock payload/errors. `evidence/api-final-environment-keys.log`. APNs production/sandbox use separate credential pairs and never fall back across environments.
- Final focused27 notification tests PASS in25.62s, including old optional-body unsubscribe scoped correctly and CSRF denied, and registration after an already materialized announcement. `evidence/api-legacy-regression.log`. This final subset includes the27 notification cases also included in the final63 suite; do not add the overlapping count as new tests.
- 30 real service mutation/consent/HTTP/document tests PASS in19.57s. New regular reservation create/status/date/edit notices reach the exact original owner; unchanged updates do not duplicate; new/returning ownership cannot receive old booking notices; transaction rollback preserves old state. `evidence/service-emit-coverage-final.log`.
- 14 completed-work photo/gallery/privacy tests PASS in4.81s, including after-completion attachments and pending-consent restrictions. `evidence/completed-work-privacy.log`.
- PostgreSQL17.11 isolated Unix-socket cluster:5 PASS in2.20s before the final APNs credential-name separation. The final provider-only delta is covered by the63 API/provider tests. Migration repeatability preserves sources; parallel receipt UUID and distinct commands preserve first acknowledgment; concurrent collector/materializer; competing token registrations one200/one409; competing worker lease only one provider acceptance. `evidence/postgresql-final-ready.log`. Earlier setup-only initdb/pg_ctl failures are preserved in prior logs; no product assertion failed in those attempts. Cluster stopped after the successful tests. An attempted repeat after that provider-only delta was stopped at local process setup (pg_ctl/postgres --version SIGKILL -9), before any database test; see evidence/postgresql-final-environment-keys.log. Parent explicitly requested no further repeat. This is not presented as a new PG pass.
- Packaged pre-deploy module and Docker context allowlist4 tests PASS in3.18s. See `evidence/packaged-migration-context-final.log` for final result; earlier test correctly found missing Docker COPY for new migration, then fixed before handoff.

## Shared live QA fixture

Loopback http://127.0.0.1:18920, actual notification/message API, synthetic SQLite with separate ios/web/android groups; opaque convenience login or fixture signed JWT, never production credentials. GET /qa/setup provides synthetic principals. Real device registration requires JWT. No real provider sending; dispatch false. History remains in ../admin-messages-qa-notifications/fixture.sqlite.

Client results belong to their owners: web reported18 live browser checks and service-worker PASS; Android reported8 main scenario groups plus3 supplemental groups PASS including actual API FCM registration/rotation and vehicle event; root owns iOS lifecycle/simulated-push evidence. These counts are not backend test counts, and the exact client source hashes are in each client's own report. Fixture does not implement full legacy vehicle detail, unrelated settings/catalog endpoints; notification authorization/navigation is proven, entire vehicle detail is not.

During live QA, Android registration exposed a real500 after an announcement had been snapshotted. Fixed by reauthorizing the current source before enqueue; regression included above. Helper-only repeated VIN collision was fixed with unique synthetic VIN, retaining history.

## Explicit unverified/unsupported scope

- Live physical APNs, FCM and WebPush delivery and current production provider configuration are not proven.
- App Store/Google Play/client release, production migration and real customer E2E are not performed by this task.
- Android admin remains deliberately excluded (ADMIN_IOS_ONLY). Admin reply push and inbound customer booking→service push are not implemented; see rollout coverage table.
- Device registration active means recorded binding, not actual delivery. Provider acceptance is not read/ack. Old released clients retain old presentation behavior; new explicit-popup behavior requires the updated client.

Deployment/backup/rollback order, field names and exact service emitter coverage: docs/operations/notification-delivery-rollout.md.
