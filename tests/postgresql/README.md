# Isolated PostgreSQL integration audit

Run from the repository root with the project virtual environment:

```sh
AUDIT_POSTGRES_BIN=/absolute/path/to/postgres/bin python -m pytest tests/postgresql -q -rP
```

Supply official PostgreSQL binaries (`initdb`, `pg_ctl`, `createdb`, `pg_dump`, `pg_restore`). The tests **never accept an existing database URL**. Every run initializes its own fresh cluster under a private `/tmp/sv-pg-*` directory, authenticates through SCRAM using a generated local password, disables TCP listening, and stops its server on teardown. Artifacts are retained for inspection. Do not use this harness to restore real customer data.

Each test gets a new database. Concurrent workers use distinct SQLAlchemy sessions/connections and exercise actual application helpers/routes. The restore test compares all registered model tables and fixture files, validates relationships, permission revocation, token revocation and subsequent inserts. No real emails, external APIs, customer records or cloud files are used.

The production system also needs separate, monitored database/storage/key backups and a recovery policy. Passing this suite is not evidence that production backups exist or a release approval.
