# Cloud test deployment

Dockerfile.cloud runs the existing API using PostgreSQL and a private Supabase Storage bucket. DATA_DIR is a disposable local cache. Required server-only configuration: DATABASE_URL (psycopg driver), DATABASE_SCHEMA, SUPABASE_URL, SUPABASE_SECRET_KEY, SUPABASE_STORAGE_BUCKET, JWT_SECRET_KEY. Never include these values in the iOS app or Git.

Use the session pooler on IPv4. A connection hook selects the application schema; pool size is capped for the free database. File keys are SHA-256 of the DATA_DIR-relative path, retaining original filenames in application metadata. Upload failures return an error instead of acknowledging a local-only write. Existing private download authorization remains in the API routes.

The restored database was copied transactionally to an isolated schema, preserving every source column and row. Legacy orphan records were retained, with foreign keys added NOT VALID for historical data and enforced for new writes. Resolve the separately recorded legacy relationship issues before validating these constraints. No automatic database reset or migration runs on deployment.

Verification performed against the cloud database from the locally running API: admin and user login; admin overview/users/services/vehicles/records/settings/audit; vehicle image retrieval; rejection of unauthenticated reads and non-admin access. Durable storage was tested by writing a new test object and retrieving it after removing only its local cache. All imported files were checked by SHA-256 and unauthenticated public download was rejected.

Render Free sleeps when idle. The app must allow cold-start latency. SMTP, paid VIN lookup credentials, push notifications, automatic subscription billing and reminder workers are not configured for this test deployment. Camera hardware investigation remains independent.

Recovery: switch the iOS test build back to the Mac endpoint. Original SQLite database and original file backups remain local. Cloud changes after migration require reconciliation before switching data sources.
