# Web admin incidents and customer analytics — evidence 2026-11-05

## Scope and boundary

Implementation lives in this isolated server worktree. No commit, push, deployment, App Store upload, production account change, real email or external AI transmission was performed by this web agent.

iOS is the functional reference. This report proves the web portion only; parent coordinates iOS and Android results. The prior ready transfer/referral package was not modified.

## Delivered web behavior

- `Aktivita uživatelů` retains historical events and offers `Řešit problém` or opens the existing persistent case. Current case status appears separately from the historical severity. Account cards show the count of open cases when supplied by the API.
- `Případy k řešení` filters active/all/individual states, with account search and paging. Red means open, amber in progress, green explicitly resolved by an administrator; dismissed is gray. No color claims application-wide health.
- A case provides the affected account, context, a read-only current-state check, safe links to existing account/tariff/vehicle/referral administration, notes and reasoned state changes. Resolving requires a verification acknowledgment. Closing the dialog is distinct from resolving the case.
- History and original events remain accessible in pages of 20; when history grows concurrently the UI requests a refresh instead of silently skipping rows. Notes and changes use version checks and a UUID. A lost response retries the same payload/UUID; conflicts never overwrite the other administrator.
- Diagnostic text must be server-marked redacted and text/plain, then shown in preview. Copy and download require separate user actions. Nothing is automatically sent to ChatGPT/Codex or any third party, and no AI repair is claimed. Denied clipboard access has a selected read-only fallback.
- A session/account-generation change removes the case dialog; stale responses cannot populate it. Customer/service authority is not expanded.
- The original hash is captured before navigation initialization so direct `#activity` and `#incidents` entry works.
- Customer dashboard analytics first reads fresh authenticated role and capability flags. Free/Basic do not preload locked analytics. Active Premium loads statistics/costs; independent flags are respected. Inactive/expired/malformed capabilities are handled explicitly. A license service error or an unexpected analytics 403 remains visible, rather than being treated as an ordinary paywall.

## Real browser/API results

Loopback fixture: `http://127.0.0.1:18917`; actual product `web_admin/index.html`, `web/customer.html` adapter, session providers, actual incident router, actual licensing service and analytics dependencies. Chrome through Playwright 1.58.2. Only the synthetic `web` actor/event group was mutated. Admin authentication was injected as a prerequisite; password/MFA flows were not tested.

### Incident flow — PASS 14

- Real Activity account → error event → persistent case
- Opening same source event is idempotent
- Read-only check identifies current Free restriction without claiming historical cause or mutating case
- Sanitized diagnostic preview + explicit clipboard and file export; no external request
- Resolution requires explicit verification acknowledgment
- Reasoned in-progress transition persists and renders amber
- Version conflict preserves other administrator work and requires refresh
- Lost response retries exact UUID/payload and creates one note
- Older history is reachable beyond initial 20 rows
- Resolved green case leaves active list and remains in All/history
- Historical red error remains immutable after case resolution
- Reopening requires reason and preserves previous resolution
- 390 px: last action visible, clickable, no horizontal overflow
- Real API denies customer and service roles

### Browser security — PASS 4

- Unredacted response cannot be displayed/copied/downloaded
- Late response after actor-generation change never renders and dialog closes
- Clipboard denied: selected read-only fallback available without external send
- Server strings render as text; arbitrary suggested URLs are not actionable

### Customer analytics — PASS 6

- Actual customer HTML/session: Free Dashboard paywall and zero analytics requests
- Basic Dashboard also makes zero locked endpoint requests
- Premium: all three real analytics endpoints render after fresh capabilities
- Reload after downgrade does not reuse earlier Premium entitlement
- License failure remains visible and is not misreported as a plan lock
- Unexpected analytics 403 remains visible

### Other checks

- Capability unit boundaries: 5 passed (Free/Basic, independent flags, expired/inactive, malformed response, privileged roles).
- Existing customer-feature input regression: 3 passed (VIN/ORV parsing, URL rejection, separate plate handling).
- JavaScript syntax and whitespace checks passed.
- Eight actual browser-loaded assets matched SHA-256 files before and after the check; see `source-pins.json`.
- Visual inspection: 1440×1000 administration/card layout, 390×844 dialog bottom control, and customer Free paywall. Last button is visible and clickable; no horizontal dialog overflow.

### Explicit limits

- The fixture is not the full deployed application. Unrelated `/health`, `/user/session/renew`, system capabilities, Comgate configuration, service contacts and reminder dispatch routes were not mounted. These fixture 404s are recorded separately; they do not constitute live production failures or full-administration verification.
- Diagnostic 409 is deliberate optimistic-lock conflict; license 503 and analytics 403 were intentionally injected fault cases. Lost response and delayed account-change response were intentionally injected browser faults.
- No real password/MFA login, paid transaction, mail delivery, deployment, production incident repair, or overall security certification is claimed.
- Related-management links invoke existing read-only entry points; their existing destructive operations were not exercised in this web incident test.
- Test history intentionally remains in the isolated SQLite fixture. No old log or case was deleted to obtain a passing test.

## Commands

Run from this worktree with fixture 18917 already running:

```sh
node tests/web/admin-incidents-live-20261105.cjs
node tests/web/admin-incidents-security-20261105.cjs
node tests/web/customer-analytics-live-20261105.cjs
node tests/web/admin-incidents-source-pins-20261105.cjs
node --test tests/web/customer-analytics-entitlements-20261105.cjs
node --test tests/security/test_customer_features.cjs
node --check web_admin/incidents.js
node --check web_admin/activity.js
node --check web_admin/admin.js
node --check web/customer-features.js
```

Browser scripts default to `/Users/toozservis/Developer/evidence-web-qa-runtime/node_modules/playwright`; override with `PLAYWRIGHT_MODULE`. They use only loopback synthetic fixtures and preserve history across reruns.

## Evidence artifacts

- [result.json](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/result.json)
- [security-result.json](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/security-result.json)
- [analytics-result.json](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/analytics-result.json)
- [source-pins.json](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/source-pins.json)
- [cases-list.png](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/cases-list.png)
- [case-in-progress.png](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/case-in-progress.png)
- [mobile-last-control.png](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/mobile-last-control.png)
- [customer-free-paywall.png](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/customer-free-paywall.png)
- [customer-premium-analytics.png](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/customer-premium-analytics.png)
- [diagnostic.txt](/Users/toozservis/Developer/evidence-admin-incidents-20261105/web-evidence/diagnostic.txt)

## Source pins at browser verification

| File | SHA-256 |
| --- | --- |
| `web_admin/index.html` | `5ccf67b1c31a15259f01f70c1fe8078c0b2654cbf8d79adebe8285e35ae2c2df` |
| `web_admin/admin.js` | `0ee7d947bae675a68b37da803879f968e3cf32e90f86957e63f32bfa0d5870b4` |
| `web_admin/activity.js` | `f3c3423bed68210a1da8f8d6b09f7ed49105a01a0059d69efd238dacd22d44c9` |
| `web_admin/incidents.js` | `b370258ae4adc32f7844f7c85bfe1e0c8b7bd17669c20763c7ac0f99af3ef0c4` |
| `web_admin/incidents.css` | `ac6c070942706c0b0f3e500647f9edf7e2ef4121681981a40ead4dfbc363f4d3` |
| `web/customer-features.js` | `113691652c7725f0f96fe2c368c21b635e0af0fa2862cc55d3ff222768ba4d12` |
| `web/customer-session.js` | `9bf363f14464693968472c9b3f5606602c5d1415d3f9a14a4d22348da478bb88` |
| `src/server/admin_session.js` | `692071bb29cc248aeda4b7aeef11dcbc85cd3083c5cec13358c786e842e1f100` |

Product files owned by this web task: `web_admin/activity.js`, `web_admin/admin.js`, `web_admin/index.html`, `web_admin/incidents.js`, `web_admin/incidents.css`, `web/customer-features.js`. API/migrations/fixture are owned by the backend agent.
