# Service-job timeline manual browser regression

The permanent CI check is `node --test tests/web/service-job-timeline.cjs` plus
the existing 225 attachment-permission cases. It checks the shared 15 vectors,
original event preservation, literal DOM rendering, local disclosure state and
the normal/guided renderer integration. It does not claim real-account UI proof.

`service-job-timeline.manual.cjs` preserves the normal-login, headed Chrome
journey used for the 2026-11-03 timeline proof. It opens a new owned browser;
it does not attach to user tabs, inject tokens, call application APIs from the
test, change clocks or provide mock positive responses. Navigation uses actual
vehicle/job cards and the existing mobile menu. All product writes are blocked.
The known reminder/Apple bootstrap POST paths remain blocked and unverified;
unknown writes fail the run. Authentication uses the normal UI and real gates.

This runner is intentionally manual and separate from the generic E2E config.
It requires an **already prepared, authorized synthetic fixture** at
`http://127.0.0.1:18879`. It never starts or seeds a server. Do not use production
accounts, production data or a production origin. Preparing a scheduler or
copying a prior GO does not authorize a new environment or source revision.

Required external run directory:

- `qa/timeline-oracle.json`: fictitious creator, owner, foreign service and
  foreign owner; vehicle/job IDs; all raw events; independent expected rows;
  six-photo event IDs; photo/document metadata; private password-file path.
- `qa/api-source-pins.json`: actual served source root and exact SHA-256 map.
- A read-only snapshot helper supporting `--output NEW_ABSOLUTE_PATH`, a frozen
  business baseline and token-free request trace, all inside `qa/`.
- A reviewed GO JSON containing `allowed: true`, `browser_allowed: true`,
  `production: false`, the exact origin and runner SHA, oracle/source-pin/helper/
  baseline hashes, helper/baseline/trace paths, and Python/Playwright/Chrome paths.
- `qa/server/fixture-password.txt`, permission mode 600, with only the authorized
  fake accounts' password. It is read from stdin and is never printed. No token,
  password or auth storage-state file belongs in the repository.

Example command, with paths supplied for the currently approved run:

```sh
node tests/web/service-job-timeline.manual.cjs \
  --run-root /absolute/path/to/approved-synthetic-run \
  --go-file /absolute/path/to/approved-synthetic-run/web-ui/approved-GO.json \
  --go-sha256 EXACT_REVIEWED_GO_SHA256 \
  --output /absolute/path/to/approved-synthetic-run/web-ui/run1 \
  < /absolute/path/to/approved-synthetic-run/qa/server/fixture-password.txt
```

The output directory must be new. Preserve failed runs; do not overwrite them or
relax expected rows to match observed output. Before and after, the runner checks
served source hashes and the frozen business data. It closes only its own browser
and leaves the independently owned fixture server running. It captures desktop,
390px, actual reload/reopen, all original event disclosures, real thumbnails,
ordinary logout and foreign-account UI absence. Direct API 403/404 assertions are
a separate real-auth API check, not credited as browser observations here.

A passing JSON is followed by personal screenshot review. Full-page captures can
leave expanded text below the dialog fold: for visual review, scroll the actual
six-originals list into the viewport and capture viewport-only desktop/390px PNGs.
Do not count a button, loader or element's existence as readable content proof.

The original actual-account run on 2026-11-03 passed 19 checks against the frozen
25-event/15-row fixture; the separate viewport observation passed four checks.
This portable copy changes only external run-root/output path resolution and has
syntax verification. It requires a newly reviewed exact harness pin before its
first run; dated evidence for the original runner does not prove a future run.
