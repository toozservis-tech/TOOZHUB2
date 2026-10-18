"""Explicit additive migration. Does not alter existing customer/license tables."""
from sqlalchemy import Integer, inspect, text
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub import models  # Registers FK targets only.
from src.modules.licensing.google_models import GoogleBillingIdentity, GoogleSubscription


def migrate_connection(connection):
    if connection.dialect.name == "postgresql":
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(810018)"))
    inspector = inspect(connection)
    for table in ("customers", "tenants"):
        if not inspector.has_table(table):
            raise RuntimeError("Google billing requires existing customers and tenants tables")
        column = next((item for item in inspector.get_columns(table) if item["name"] == "id"), None)
        if not column or not isinstance(column["type"], Integer):
            raise RuntimeError("Google billing foreign key type requires review before migration")
    for table in (GoogleBillingIdentity.__table__, GoogleSubscription.__table__):
        table.create(connection, checkfirst=True)
        present = {column["name"] for column in inspect(connection).get_columns(table.name)}
        if set(table.columns.keys()) - present:
            raise RuntimeError("Existing Google billing schema is incomplete; no existing columns were changed")
        expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete)
                        for fk in table.foreign_keys}
        actual_fks = {(fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0],
                       (fk.get("options") or {}).get("ondelete")) for fk in inspect(connection).get_foreign_keys(table.name)}
        if not expected_fks <= actual_fks:
            raise RuntimeError("Existing Google billing foreign keys require review")
        expected_indexes = {index.name for index in table.indexes}
        actual_indexes = {index["name"] for index in inspect(connection).get_indexes(table.name)}
        if not expected_indexes <= actual_indexes:
            raise RuntimeError("Existing Google billing indexes require review")
    unique_columns = {tuple(item["column_names"]) for item in inspect(connection).get_unique_constraints("google_billing_identities")}
    if ("customer_id",) not in unique_columns:
        raise RuntimeError("Google purchase identities require a unique customer binding")


def migrate(bind=engine):
    with (bind if bind is not None else engine).begin() as connection:
        migrate_connection(connection)


if __name__ == "__main__":
    migrate()
    print("Google billing schema ready; existing licenses and accounts retained.")
