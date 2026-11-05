# Notification inbox and push rollout — 2026-11-05

This change is prepared locally, not deployed by this work item. Production push sending is not verified. Root owns release/deploy coordination.

## Required order

1. Preserve an encrypted, restorable database backup using the established recovery procedure. Do not copy customer data into QA.
2. Integrate the reviewed backend and matching iOS/web/Android recipient clients. Keep `PUSH_DELIVERY_ENABLED=false` (also the default).
3. Build with `requirements-server.txt` including `httpx[http2]`; `Dockerfile.cloud` and its context include `scripts/migrate_notification_delivery.py`.
4. Run the actual pre-deploy command `python -m scripts.migrate_mobile_release`. It runs additive 0029 after 0028. Fresh-process packaged tests run this command twice. Alembic revision 20261105_0029 also exists, down_revision 0028; the Render runner is the explicit module command, not an implied Alembic invocation.
5. Confirm the six tables and indexes exist: notification_items, notification_commands, notification_announcement_policies, notification_devices, notification_push_outbox, notification_cursors. Existing source history remains in admin_messages, system_notifications and vehicle_updates.
6. Start the application. Every process can collect; database source cursors and recipient locks serialize collection. Push outbox leases/CAS prevent two concurrent workers claiming one send. A cycle runs every 15 seconds, collector source limit100 and fanout500, up to50 sends per cycle when enabled.
7. Verify authenticated inbox and explicit read/dismiss/ack against authorized test recipients. GET does not mark read. Pending means unread or action requiring the recipient, not provider acceptance. Do not use real customers as involuntary test recipients.
8. Configure provider credentials through existing secret storage. Keep dispatch false while setting `PUSH_DELIVERY_RECIPIENT_IDS` to the explicitly authorized test account's positive numeric ID. Only then enable dispatch for that canary. The allowlist applies to all its active devices/providers, not just one installation; verify the test account's intended devices first. Use one new targeted message after rollout, never a broadcast or a real customer as QA. Test foreground, background/closed app, badge, tap→authorized detail, read vs explicit confirmation, logout/account switch, revoked token, and offline recovery. Provider HTTP acceptance is not evidence of device display. General dispatch is a separate operator decision, not an automatic result of the canary test.

## Configuration names (never values in reports)

- PUSH_TOKEN_ENCRYPTION_KEY: stable Fernet key for encrypted device tokens. Preserve with recovery secrets. Do not rotate without a token re-encryption/re-registration plan.
- PUSH_DELIVERY_ENABLED: false initially; enable only after provider/device proof.
- PUSH_DELIVERY_RECIPIENT_IDS: optional comma-separated positive decimal account IDs. Whitespace around IDs is accepted; zero, negatives, empty elements, wildcards, nondecimal text and overflow fail closed. An absent/blank value allows general delivery only when PUSH_DELIVERY_ENABLED is true. Set the canary list before enabling; removing it while enabled broadens delivery. The filter is checked before a lease is claimed and again immediately before provider invocation. Excluded rows keep state/attempts and cannot starve eligible rows; configuration changes after claim release that claim without consuming a delivery attempt. No IDs are returned by public readiness. Process environment changes require replacing/restarting each worker; already accepted provider requests cannot be recalled.
- APNS_KEY_ID/APNS_PRIVATE_KEY for production; APNS_SANDBOX_KEY_ID/APNS_SANDBOX_PRIVATE_KEY for sandbox; shared APNS_TEAM_ID/APNS_BUNDLE_IDS. There is no fallback between environment key pairs. Development-signed apps use sandbox, App Store/TestFlight production, matching actual entitlement. Signing capability and profile must support push.
- FCM_PROJECT_ID, FCM_SERVICE_ACCOUNT_JSON, FCM_BUNDLE_IDS; matching Android Firebase project/build configuration.
- VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_SUBJECT; existing WEB_PUSH_ENABLED controls legacy web opt-in availability.

`GET /api/v1/push/device-status` exposes configuration presence, not credential validity: registration_available, dispatch_enabled, dispatch_limited, dispatch_configuration_valid, providers.<platform>.configured. A malformed canary list makes dispatch_enabled false. Limited mode does not disclose or promise that the current account is included. Registration2xx/active only means a session-bound encrypted binding was saved. It does not mean sending is enabled, or that any notification reached a device.

## No historical push backlog

First migration seeds each durable source cursor to the existing maximum ID with rollout_at. Existing history remains readable without generating old OS notifications. Re-running migrations retains cursor positions, history and receipts. New authorized sources after rollout can enqueue; read/dismiss/ack and current authorization suppress sending. Registering after an eligible new unread event can queue it, but events older than24h are skipped. Scheduled announcements measure this age from their start, not their authoring date; audience is rechecked at send time. Scheduled candidates have no private snapshot until eligible. Newly registered accounts outside the collector's original audience can read an applicable announcement on app open; no claim is made of retroactive OS delivery to them.

## Safety and privacy

- Only active user/service recipients; admin remains sender/auditor through existing admin APIs, protected by current administrator verification.
- Recipients cannot list/read/confirm another account's data. IDs from pushes are untrusted until refetched through authenticated API.
- Normal admin message/announcement: open = read; explicit Rozumím = durable dismissal. Required message: explicit Potvrdit přečtení = acknowledgment. Reply does not implicitly acknowledge required messages.
- Announcement content is snapshotted only for an eligible recipient so expired/deactivated notices remain that recipient's archive. Archive is not badge/popup/push. Receipt history is never deleted by reading.
- Service events retain original recipient, exact active ownership ID/epoch, and consent publication rules. Old booking notifications cannot follow a vehicle to another owner or a later ownership epoch.
- Provider payload is generic, with notification ID/kind/badge/route only. No private text, email, VIN, plate, invoice or token in lockscreen payload/logs. Browser endpoints are HTTPS allowlisted; redirects disabled.
- Installation secret prevents arbitrary reassignment of a known token. Devices bind recipient, exact session digest/version/expiry and generation. Server logout (also logout ticket) revokes binding atomically. Offline logout cannot inform an offline server immediately; durable client logout retry/session expiry remains necessary.
- Provider responses are stored only as bounded classified codes. APNs410/FCM UNREGISTERED/web404 or410 revoke binding; other FCM INVALID_ARGUMENT does not automatically revoke.
- At-least-once provider delivery: after a crash between provider acceptance and DB receipt, a generic notification may repeat. Stable collapse/tag limits duplicates. Receipt commands are UUID idempotent; confirmation timestamp is set once.

## Service event coverage

| Business mutation | Publication to customer | Evidence / boundary |
|---|---|---|
| Service creates regular reservation | booking.created | New generic event, original current owner only; consent remains unchanged. |
| Service changes regular reservation status, date or description | booking.confirmed/cancelled/completed/rescheduled/updated | One event per actual change; unchanged retry does not create another. No reservation notes copied. |
| Service responds to quick booking | booking.confirmed/proposed/rejected | Existing explicit emitter; no duplicate reservation on retry. |
| Service requests vehicle access | access_request.created | Generic request only. Reading does not approve. |
| Owner approves request with private saved work | job.shared | Work is published after explicit owner consent. |
| Owner approves/rejects a request without saved work | No new service-origin event | This is the owner's own decision, not new work from service. |
| Job intake/start/progress/completion/handover | job.received/in_progress/updated/completed/handed_over | Only owner-visible jobs; private pending work excluded. |
| Job photo/PDF, including photos after completion | job.photo/document | Only after consent. Original job/history retained. |
| Manual service record and persisted attachments/edits | record.created/document.added/record.updated | Existing transactional ORM hooks; abandoned upload never publishes. |
| Repair photo session/photo, vehicle/reminder updates | repair.created/photo_added/vehicle.updated/reminder.updated/deleted | Existing actor-scoped transactional hooks; owner/self/scheduler does not masquerade as service. |

Not implemented by this release: booking created/cancelled by customer → service OS push, access-decision → service OS push, and recipient reply → admin OS push. Existing booking e-mail/API and admin conversation inbox remain; no universal all-role push claim is justified.

## Rollback / operational limits

Disable PUSH_DELIVERY_ENABLED first if provider delivery is wrong. This stops future worker sends; already provider-accepted notifications cannot be recalled. Keep tables/cursors/receipt history. Roll back application code only; destructive migration downgrade is deliberately refused. Do not restore an old database over newer customer data or replay source IDs to force a retry. Failed/blocked outbox rows and provider readiness require operator investigation before a bounded authorized retry.

No new paid worker/resource is provisioned. Production config/readiness and actual APNs/FCM/WebPush physical delivery remain unverified in this local work item. SQLite/PostgreSQL provider mock tests and native simulated push are not live provider tests.
