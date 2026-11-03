# Ownership archive detail browser regression

This candidate is separate from service-record soft-archiving. It never replays
the historical record2–7 DELETE journeys. It uses the frozen synthetic ownership
oracle and a real headed Chrome against `http://127.0.0.1:18879`.

Run `launch.py --go-file <run>/web-ownership-ui/runtime-go.json --output <run>/web-ownership-ui/runNEW` only after fresh root iOS archive UI authority and explicit GO. The GO must contain:

- `allowed`, `readonly_product`, `allow_safety_network_abort`: true; exact `origin` above.
- `project_root`: actual reviewed product tree; `source_sha256`: every relevant inspected source.
- `ios_authority_path`, `ios_authority_sha256`: fresh actual native UI proof, not a source-only review.
- `oracle_file`, `oracle_sha256`: final frozen ownership oracle.
- `harness_sha256`: exact `archive-detail.cjs` bytes.
- `repair_metadata_file`, `repair_metadata_sha256`: read-only expected metadata from the same frozen fixture; no invented values.
- `business_snapshot_helper`, `business_snapshot_helper_sha256`: frozen fixture read-only snapshot helper.
- `frozen_business_baseline`, `frozen_business_baseline_sha256`: approved epoch2 baseline; the pre-browser snapshot must equal it.
- `allowed_ambient_safety_abort_paths`: exactly `['/api/v1/reminders/check-and-send-notifications']`; this POST remains blocked and unverified.
- `node_binary`, `playwright_module`, `chrome_binary` as needed on the current host.

The password comes only from the oracle's mode0600 fixture file through stdin.
The harness uses normal login forms and UI buttons, observes actual response and
download bytes, checks literal private values/HTML, both PDF variants with dedupe,
three private images, an actual decoded repair-photo preview with verified SHA and
source/author/separate UTC capture/upload metadata, a private repair-report PDF
download directly from the former-owner archive, reopen/reload, 390px layout, logout and
a new-owner login. Services retain their currently hidden archive UI. Real JWT
API denial proof remains separate; UI absence alone is insufficient.

Only ordinary auth/telemetry requests, logout and product GET/HEAD/OPTIONS are
allowed. External traffic and product writes are aborted and recorded. The exact
ambient reminder POST is counted separately as blocked; all archive/unknown
mutation attempts fail. Do not claim zero attempted business writes globally.
Exact bytes come from native UI download artifacts. Empty/unavailable CDP-body
observations are retained as diagnostics; MIME, no-store/non-public cache policy
and nosniff remain required. No token
injection, evaluation, internal action calls, positive API mocks, clock override,
visibility override or automatic retry is used. Every output directory is new;
all failures remain evidence. Business data/files and product source hashes must
match before/after. Repair preview object URLs are cleaned on close/remove/logout/error,
with delayed-account/response tests in `test_ownership_repair_preview.cjs`; the browser
journey checks actual image.onload dimensions, visible image and removed-image state.
Native PDF preview, physical devices, production and
hosted CI are outside this browser scope.
