# Google Play subscriptions — release and verification

Implementation date: 18 October 2026. This is a deployment checklist, **not evidence of a live purchase**. The Play Console account, product availability, production signing, API permissions and real purchases still require live verification. This release is safe to deploy with `GOOGLE_PLAY_ENABLED=0` (or unset): the app must show unavailable purchasing, not simulate successful payment.

## Android/server contract

Production application ID: `cz.toozservis.spravavozidel.android`. The `.preview` variant cannot purchase the production catalog. No API accepts a client-selected package, price, plan, expiry, success boolean or customer ID as proof of payment.

| Product ID | Base plan ID | Access | Period |
|---|---|---|---|
| `evidence_vozidel_basic` | `monthly` | Basic, 5 vehicles | Monthly |
| `evidence_vozidel_basic` | `yearly` | Basic, 5 vehicles | Yearly |
| `evidence_vozidel_premium` | `monthly` | Premium, unlimited vehicles | Monthly |
| `evidence_vozidel_premium` | `yearly` | Premium, unlimited vehicles | Yearly |

These are auto-renewing base plans. Offers/trials, prepaid plans and concurrent add-ons are deliberately not enabled. Android must display localized Play `ProductDetails` prices and the matching base plan's offer token, never a hard-coded amount. Intended Czech prices require matching console price tiers: Basic 149/1,490 CZK; Premium 449/4,490 CZK. Do not silently substitute a price.

Authenticated endpoints under `/api/v1/license/google`:

- `GET /catalog`: `{enabled,message,package_name,products:[{product_id,base_plan_id,plan,period,vehicles_limit,features}],...snapshot}`.
- `POST /session`: `{can_purchase,reason,message,obfuscated_account_id,package_name,...snapshot}`. Reasons: `not_configured`, `account_ineligible`, `other_provider`, or null. Ownership conflicts return 409. Pass the opaque ID unchanged to BillingFlowParams `setObfuscatedAccountId`; it is not the email address.
- `POST /sync`: body `{purchase_token:"..."}`; result `{verified:true,acknowledgement_pending,...snapshot}`. Only invoke after BillingClient reports PURCHASED. A pending transaction does not grant access.
- `POST /restore`: body `{purchase_tokens:["..."]}` (max 20). Result `{verified:true,restored_count,rejected_count,acknowledgement_pending,...snapshot}`. Rejected tokens do not move between app accounts. A transient Google outage is 503, not a successful empty restore. Six calls/account/minute; throttle automatic foreground restores at least 60 seconds.
- `POST /reconcile`: no purchase token in the body; checks up to three known server purchases older than 60 seconds; returns `{verified:true,checked,...snapshot}`. It cannot discover a never-synced purchase; use BillingClient queryPurchases + restore for that case.
- `POST /notifications`: authenticated Google Pub/Sub push only, no app bearer. Never accept a caller's notification state as entitlement proof.

Snapshot fields: `plan`, `provider`, `status`, `billing_period`, `expires_at`, `auto_renew`. Existing license/status API remains the authority for feature flags. A Google obligation can have `status=pending/on_hold/paused` with `plan=free`; offer management of the existing Play subscription rather than selling another payment provider. `cancel_at_period_end` retains paid access until Google's verified expiry. Grace access ends at the verified expiry too.

## Server configuration (secret store only)

- `GOOGLE_PLAY_ENABLED=0` until all live release gates below pass.
- `GOOGLE_PLAY_PACKAGE_NAME=cz.toozservis.spravavozidel.android` (hard allowlist; preview rejected).
- `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`: dedicated service account credential JSON with `type=service_account`, official OAuth token URI, private key and client email. Keep it in Render secrets, never Android, Git, screenshots, chat or test fixtures. Configure least necessary Play app access for viewing and managing purchases/subscriptions; enable Android Publisher API.
- `GOOGLE_PLAY_TOKEN_KEY`: persistent Fernet key generated in the secret-management workflow. It encrypts purchase tokens for future reconciliation. Back it up privately. Do not replace it without an explicit re-encryption migration; loss of the key breaks token reconciliation.
- `GOOGLE_PLAY_PUSH_AUDIENCE`: exact HTTPS URL configured as Pub/Sub OIDC audience, normally `https://app.toozservis.cz/api/v1/license/google/notifications`.
- `GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT`: exact Pub/Sub push service-account email. Signature, audience, Google issuer and verified email must all pass. Grant the Pub/Sub service agent permission to mint tokens for this identity.
- `ENABLE_GOOGLE_RECONCILIATION_WORKER=1` (default 1): worker wakes every minute; verified live subscriptions normally checked every 15 minutes; acknowledgement retries after one minute, failures back off to six hours. Multiple instances use durable leases plus tenant locks. Do not disable both RTDN and reconciliation.
- `GOOGLE_PLAY_ALLOW_TEST_PURCHASES=0` (default): only set to 1 for license testing together with `GOOGLE_PLAY_TEST_CUSTOMER_IDS` containing numeric IDs of dedicated test app accounts. Both conditions are required; never allow a real customer to receive test entitlements by accident. App-account IDs belong only in the server configuration, not the distributed APK.

`google-auth>=2.40,<3` is in requirements-server.txt; Docker installs it. No Google key is bundled. Publisher network timeouts and OAuth-refresh timeouts are bounded. Application telemetry logs only route, method, status and duration; it does not collect request bodies or authorization. Raw purchase tokens never appear in application responses or logs; the HTTP transport's token-bearing URL paths are redacted even under debug logging.

## Additive database/deployment sequence

1. Keep Google billing disabled. Back up the production database using the existing private backup procedure.
2. Review the combined release diff. This checkout also contains a separate inbox migration 0017; Google is 0018.
3. Install/build the server image from the reviewed source. Docker includes the explicit migration script.
4. With the deployment's existing database connection, execute `python -m scripts.migrate_mobile_release`. Its Google step is `python -m scripts.migrate_google_billing`, which can also run separately after the image is available. Do not print database credentials.
5. Google migration creates only `google_billing_identities` and `google_subscriptions` plus indexes/constraints. It checks referenced tables, integer key types, foreign keys and unique customer binding. On PostgreSQL it runs in a transaction with advisory lock 810018, lock timeout 5s and statement timeout 60s. It neither alters current license tables nor changes any account or tariff. It is repeatable. An incomplete pre-existing Google schema fails rather than guessing an alteration.
6. Deploy the server with Google still disabled. Verify existing login, customer/service workflow, Apple catalog/status and Comgate checkout protections. Google catalog must report `enabled=false`; session must report `can_purchase=false`.
7. Configure credentials privately, create and activate the exact base plans in the correct Play Console app, configure RTDN Pub/Sub topic/permissions/authenticated push, and publish a signed internal-testing AAB using the production package. Install from Play internal testing; a locally installed preview does not prove Play Billing works.
8. Once settings are reviewed, enable Google for the controlled test. Test with dedicated app accounts and Play license testers; do not make or imply a real-money purchase without user authorization.

Rollback: set `GOOGLE_PLAY_ENABLED=0` to stop new Google operations while diagnosing. This also pauses verification, so use only temporarily; verified access still expires at its last confirmed validity. Do not delete the Google tables, bindings or token-encryption key, and do not downgrade to an implementation that cannot enforce Google expiry or cross-provider protections. Retain anonymous purchase ownership tombstones after account deletion to prevent purchase transfer.

## Required live acceptance evidence

- Correct four localized offers and package; preview has purchasing disabled.
- Basic purchase, server acknowledgement, Basic feature/5-vehicle limit, restore and restart.
- Upgrade Basic → Premium; old token cannot restore Basic after replacement or refund.
- Deferred Premium → Basic / billing-period change: current paid plan remains until the Play renewal; new plan applies only after the new item is owned and has a valid expiry.
- Cancel renewal retains paid access until expiry; expiry removes only entitlement, never stored vehicles/documents.
- Pending payment, grace, hold, pause, recovery, revocation/refund with revoked access; verify API state and client-visible plan separately.
- Same purchase restored into a second app account is rejected and second account remains unchanged. Test deleted-account tombstone separately using a disposable account.
- Existing Apple/Comgate/manual paid plan blocks Play purchase; Google subscription (including hold/pause) blocks a second provider. Late Comgate callbacks cannot overwrite Google/Apple.
- Signed Pub/Sub test accepted; unauthenticated push and wrong service-account identity rejected. Deliver duplicate/out-of-order RTDN and verify current Publisher state wins.
- Simulate lost RTDN and a temporary Google outage: reconciliation corrects state; failed checks never invent entitlement or reset last verified expiry. Verify worker aggregate logs without tokens.

Automated tests use synthetic Google responses and isolated SQLite only. They are not a live Play purchase or a real PostgreSQL multi-process concurrency test. Record live transaction/account evidence privately, without saving purchase tokens, credentials or OTPs into public artifacts.

## Primary documentation checked

- [Verify purchases, bind accounts, acknowledge on the backend](https://developer.android.com/google/play/billing/security)
- [subscriptionsv2 resource, line items and states](https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2)
- [subscriptionsv2.get](https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptionsv2/get)
- [Subscription lifecycle, deferred replacements and out-of-app resubscribe](https://developer.android.com/google/play/billing/lifecycle/subscriptions)
- [Server acknowledgement](https://developers.google.com/android-publisher/api-ref/rest/v3/purchases.subscriptions/acknowledge)
- [Authenticated Pub/Sub push](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
