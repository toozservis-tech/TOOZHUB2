# Web quick-request decisions and reverse notification integration — 6 November 2026

Status: **OVĚŘENO for the bounded real Chrome scenarios below**, with normal password authentication against actual isolated API18926. **Full three-client shared quick-decision parity remains unverified.** No canonical changes, production changes, deploy or real provider sends.

## Scope and source provenance

- Isolated branch `codex/web-booking-decisions-20261106`, base `7c17b626d1cec7626bb6721fe0fadba8ff6df21b`.
- Frozen backend `6b24003376ee8140f1650ac18075ae13b754029f`, loopback API18926. Actual business routers, normal password login, no injected JWT/session, no browser hidden-runtime API calls.
- Inherited four reverse notification files from immutable18927 candidate (admin-messages.js, notification-center.js, sw.js, web_admin/index.html). Quick-request implementation extends notification-center.js; the original candidate is preserved.
- Initial full UI run used pinned proxy18928; focused final copy/refresh retest used separate pinned proxy18929. All original18927/18928 evidence remains intact. See sibling `qa18929/final-provenance.json` for actual18929 origin/freeze time, superseding inherited metadata only in its original source-pins file.
- Existing reservation list/calendar previously lacked quick-request decision UI. One ServiceBookings module now supplies exact-ID list/detail/actions to both notifications and existing Reservations/Calendar.

## iOS reference and action mapping

Reference: `/Users/toozservis/Developer/evidence-notification-actions-20261105/ios/Sources/TooZHub/Views/QuickServiceBooking.swift`, `BookingRequestDetail` lines 287–376 and DTOs near lines 3–77. Reservations integration follows `ReservationsView.swift`. Reference hashes are recorded in the manifest.

| Current role / state | Available action | Server result |
|---|---|---|
| Assigned service, pending with preferred date | `accept` | Confirm preferred future date; create one confirmed reservation |
| Assigned service, pending or proposed | `propose` | Save a future proposal; owner confirmation still required |
| Assigned service, pending or proposed | `reject` | Require a reason; preserve rejected request/history |
| Current owner, proposed | `accept_proposal` | Confirm proposed future date; create one confirmed reservation |
| Current owner, pending or proposed | `cancel` | Preserve cancelled request/history |
| Confirmed, rejected or cancelled | None | Read-only history; exact existing reservation link if present |
| Other account or administrator | None | No workspace data or decision form |

Every decision uses `POST /api/v1/service-booking-requests/{exact id}/decision` with immutable `{client_id: UUID, expected_version, action, message, proposed_datetime}`. Message is at most 2,000 characters; reject requires a nonblank reason. Local datetime input is explicitly converted to ISO UTC; the UI labels the browser timezone. Past, malformed or normalized invalid wall times are rejected. No service access grant is created by client code.

While a command is running, the UI says `Ukládám…`, disables changes and rejects duplicate submission. Network/5xx/invalid responses retain the exact command for retry; the retry does not create a new UUID or change body/version/action. Pending command is memory-only, not a promise of persistence across browser restart and not stored as plaintext in browser storage. Reload must reread the server state. The API's version check prevents blindly reapplying a stale decision.

Known rejection clears the command; HTTP 409 requires an explicit refresh before a new action. HTTP 401/403/404 removes stale private details. Account/session change invalidates in-flight results and closes the old workspace. A success response must identify the same participant request and advance its revision before the UI says the answer was saved.

## Exact files

- New `web/booking-requests.js`: the shared list, exact-ID detail and decision workspace.
- `web/notification-center.js`: delegates quick-request actions to that module; removes the earlier read-only duplicate renderer.
- `web/index.html`: loads the asset and inserts the list into existing reservations surface.
- `web/legacy-app.js`: refreshes quick requests through existing reservations entry.
- `web/notification-center.css`: scoped responsive form/history styles using the existing scrollable dialog.
- `src/server/web_access.py`: adds only `booking-requests.js` to the exact public static JS allowlist. No route/auth dependency changes.

The anonymous asset contains program code, not account data or secrets. All data and commands still use authenticated session requests and the existing exact participant API. Publishing a JS asset does not authorize an API action.

## Final follow-up

Actual testing found that accepting a proposal updated quick-request history but left the regular reservation list stale until re-entry. After a confirmed business response the module now refreshes `loadReservations(true, {preserveModal:true})`. This preserves the open result, checks the session before rendering and distinguishes saved-business state from a failed list refresh. Refresh failure never restores a command or creates a second mutation. Neutral service label is “Zpráva pro zákazníka”; rejection still explicitly requires a reason. A network TypeError has Czech text, without hiding HTTP403/409.

## Evidence and results

All paths below are relative to `/Users/toozservis/Developer/evidence-web-booking-decisions-20261106/`.

| Scenario | Result | Evidence |
|---|---|---|
| Service normal UI login; accept preferred date | OVĚŘENO; quick7 confirmed v2 → reservation5 | qa18928/runtime/02-service-accepted.*, 03-related-reservation.* |
| Service propose date, 390×844, bottom close reachable | OVĚŘENO; quick8 proposed v2, local14Nov10:30 | qa18928/runtime/04-proposal-mobile-before.*, 05-proposal-mobile-bottom.* |
| Empty rejection blocked; valid reason terminal history | OVĚŘENO; quick9 rejected v2 | qa18928/runtime/06-reject-reason-required.ax.txt, 07-service-rejected.* |
| Notification → exactquick11 | OVĚŘENO; same single decision workspace | qa18928/runtime/08-exact-notification-request.* |
| Second UI login closes previous session/old private modal | OVĚŘENO; not claimed as two-UI409 | qa18928/runtime/10-prior-session-closed.* |
| Independently password-authenticated HTTP peer changes request while browser holds old version | OVĚŘENO; actual409, explicitrefresh, no overwrite | qa18928/runtime/concurrent-change.json, 11-conflict409.* |
| Own proxy unavailable, retry saved once | OVĚŘENO browser behavior; exact UUID/body identity separately covered by JS unit | qa18928/runtime/12-network-failure.*, 13-retry-success.* |
| Owner UI accept proposal and cancel pending | OVĚŘENO; quick8confirmedv3/reservation6; quick10cancelledv2 | qa18928/runtime/14-owner-accepted-proposal.*, 15-owner-cancelled.* |
| Owner reload and resolved history | OVĚŘENO | qa18928/runtime/16-owner-reload-history.* |
| Final neutral label + required empty rejection | OVĚŘENO final18929bytes | qa18929/runtime/01-neutral-rejection.* |
| Final Czech network failure; exact same UI retry stored one event | OVĚŘENO final18929bytes; quick11v4→v5 | qa18929/runtime/02-czech-network-error.*, 03-retry-saved.*, readback.json |
| Final owner acceptsquick11, closes result, sees new regularreservation immediately without reload/re-entry | OVĚŘENO final18929bytes; quick11v6/reservation7confirmed | qa18929/runtime/04-owner-confirmed.*, 05-immediate-reservation.ax.txt, 06-new-reservation7.* |
| Same shared iOS reply16→A14 history and notice49 pending | OVĚŘENO web normal shared-owner login; A ACK remainsnull; no reply/ACK/business mutation | qa18929/runtime/07-shared-A-pending.*, 08-shared-ios-reply-history.*, readback.json |

Opening shared communication displayed B15, so the application marked that visible message and its notice50 read. This is a real incidental **read mutation**, not a claim the whole shared database was untouched. A14/notice49 still unacknowledged. Quick6 remains pending/version1; no shared booking decision was performed. Android shared ACK was blocked by emulator access; it is not claimed complete.

## Focused offline checks

- `node tests/web/booking-decisions-unit-20261106.cjs`: **27PASS**, actual product functions in isolated DOM/session stubs. Includes role/state/exactID, immutableUUID retry,403/404 clearing,409refresh, account races, literal-text rendering, final copy and actual legacy-loader success/failure/session checks. `evidence/unit-final.log`.
- `tests/web/test_booking_asset_20261106.py`: **1PASS**, actual static gate class with denied authstub; noDB. Exact publicJSbytes only; protected HTML and backup/map paths still gate. `evidence/static-asset.log`. This does not substitute for browserauth.
- JS syntax and `git diff --check`: PASS.
- Inherited reverse message/source-reference/role tests are retained as `reverse-notifications-unit-20261105.cjs`; previous frozen18927 Chrome evidence remains separately pinned.

The earliest static-test failure was a test-only assertion accidentally rejecting existing public `reset-password.html`; that assertion was removed and evidence retained. Product auth was not weakened.

## Limitations / handoff

- Pending quickdecision UUID/body are in memory only, not durable across reload. The browser interruption test proves retry UI and one resulting history event; it does not inspect browser-hidden state or independently capture identical wire UUID on an unreachable first attempt. VM does check exactUUID/body reuse.
- UI uses final18929sources for focused follow-up; earlier complete role matrix remains18928proof and is not relabeled as a full final-source rerun. Same shared A/reply history was inspected on final18929bytes.
- Existing frozenAPI fixture mounts `/web` as plain StaticFiles (HTML200); `/web_admin` uses actual guard. Proxy preserves upstream status/security headers and adds exact new publicJS only. Product static guard is separately tested; normal data and command APIs remain authenticated/participant-limited.
- No WebPush/APNs/FCM provider delivery is tested here. Disabled providers are not a successful physical notification delivery.
- Full same-object quick6 decisions across iOS/Android/web are still pending parent coordination. iOS is the source reference; Android administration remains intentionally excluded.
- Commit is an isolated review candidate, not production deployment or canonical integration.
