# Private admin messages — web validation, 5 November 2026

## Scope and state

Implemented in isolated worktree `/Users/toozservis/Developer/evidence-admin-messages-20261105/server`, on backend commit `1228a4ef9aa3a6d5d45a662566fd9527a012b0ed` (original task baseline `e84bdac`). No production deployment, real-user message, e-mail, push, App Store upload, or canonical integration was performed by this agent. iOS and Android results are owned by the coordinating agents; this report certifies web scenarios only.

Admin has a global **Zprávy** section plus **Napsat zprávu** in the actual account detail for user/service roles. Both recipient profiles have **Zprávy administrace**, separate from existing service/vehicle updates. Startup summary is checked after authentication and on return to the visible page; the banner opens **Nové a k potvrzení**, while the profile opens full history.

Incoming message bodies are marked read only after intersection with the viewport in a focused, visible document. GET/summary alone never marks read. An explicit required acknowledgment remains pending after opening and after reload until **Potvrdit převzetí**. Receipt timestamps come from server DTOs, not the browser clock. Admin wording distinguishes server storage from device delivery. No message edit/delete was introduced.

The existing admin/customer session provider handles authentication, authorization freshness, CSRF and same-origin transport. A late response from an old session cannot render a body or send a read receipt. The UI uses text nodes, not HTML, for message content and recipient data.

Uncertain send retries use the identical payload and UUID. Across a page reload, sessionStorage retains only UUID, SHA-256 of the exact body/ack option and a creation time; it does not retain the private text. The user is told to inspect history, and re-entering the same text/option reuses that UUID. Session-end clears this metadata. This is same-browser-session recovery, not a promise of recovery after closing a browser session or on another device.

## Actual browser results

- **PASS 12** live scenarios: real admin account entry/send; startup/GET do not read; visible ordinary message read and banner cleared; required acknowledgment survives open/reload; recipient reply/history; admin inbox/read/ack; service profile acknowledgment/reply; lost-response exact retry; same retry after reload using hash-only metadata; old pending message plus stable cursor/new arrival; 390px bottom controls; actual role/other-account denial.
- **PASS 4** security scenarios: XSS text rendering; unfocused tab does not mark read; session replacement rejects stale body/read; API refuses recipient requires_ack injection and other-account receipts.
- **PASS 8 source pins**: browser response bytes match eight source/provider files. Both actual customer/service HTML and actual admin HTML were loaded.
- `node --check` for changed JavaScript and `git diff --check` passed.
- Desktop receipts and narrow last-control screenshots were visually inspected.

The Chromium browser was launched by Playwright 1.58.2 with its installed Chrome channel. The focus scenario explicitly disables Playwright’s default `Emulation.setFocusEmulationEnabled=true`, then switches actual browser tabs. It does not patch `document.hasFocus()` or visibility flags.

## Reproduce

```sh
cd /Users/toozservis/Developer/evidence-admin-messages-20261105/server
node tests/web/admin-messages-live-20261105.cjs
node tests/web/admin-messages-security-20261105.cjs
node tests/web/admin-messages-source-pins-20261105.cjs
git diff --check
```

Requires the backend agent’s loopback-only actual API fixture `http://127.0.0.1:18918`. Scripts refuse non-loopback origins. All mutations target the synthetic `web` group only. Repeated runs preserve prior message history; the test precondition reads/acknowledges earlier synthetic messages. Long pagination history is created by the fixture-only seed helper to avoid weakening real product send-rate limits.

Evidence folder: `/Users/toozservis/Developer/evidence-admin-messages-20261105/web-evidence`

- `live-result.json`, `security-result.json`, `source-pins.json`
- `admin-conversation-receipts.png`, `user-acknowledged.png`, `service-reply.png`, `mobile-last-control.png`

## Explicit limits

Authentication is a synthetic JWT precondition; password, MFA, actual session renewal and a production push/e-mail system were not tested. The fixture lacks unrelated health, capabilities, Comgate, service-workspace, account-security and renewal endpoints. Their observed 404s are listed in `live-result.json`; no message endpoint was mocked or replaced with fake UI responses. Send-response loss is deliberately injected after the real API commit; read/ack/send state is then verified against the actual API. No external requests occurred in the final live run.

## Changed files and source SHA-256

- `web/admin-messages.js` — `e2b4647c3ce0009b6fd3d76d11427bf58a2e499ec3daa31c609fae35dc385085`
- `web/admin-messages.css` — `e64e138e1a6014667196cdadf34ee372ef74d96a404bd0f0aae69ab73d59f650`
- `web/customer-features.js` — `9eea189e80a03c1caffff727932f4d479de87c0fd501e28b94537a26f0230be4`
- `web/legacy-app.js` — `725edc4f7c6192f3bca681d9b15f46ca0235e3db765e5eaad64ae8fe2d32ba77`
- `web_admin/admin.js` — `e43813eb20d20cca82a83fa9ce9b8714978a4c845261ee79725dd14ee16258d6`
- `web_admin/index.html` — `1544885e631d730111bd12876b5d3d6f4fc123f65623484681a3b24e6aabcbca`
- `tests/web/admin-messages-live-20261105.cjs` — `5afad92132ec8047a30cf4874d6ef3336f78791ee0491e5fcb8127069b3c5a07`
- `tests/web/admin-messages-security-20261105.cjs` — `3b4d8d65f39e7aaeca0e985560fa9e3fa5c5c288332f0bee878c2882ee1ff659`
- `tests/web/admin-messages-source-pins-20261105.cjs` — `52dd1a79f34d882fc0ef4df5e7346903bda0c4375b81696d7c57810bc460ee5d`

The source-pins artifact additionally contains the unchanged `web/customer-session.js` and `src/server/admin_session.js` hashes used by the browser. Python-owned mounts/whitelist are in backend commit1228a4e.
