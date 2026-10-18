"""Guard against startup DDL against an already migrated live VIN table."""
from types import SimpleNamespace

from scripts.migrate_workshops_vehicle_identity import migrate_connection


class _ExistingGuardDatabase:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.probes = 0

    def scalar(self, query):
        self.probes += 1
        sql = str(query)
        assert "sv_vehicle_vin_guard" in sql
        assert "vehicle_vin_claims" in sql
        return True

    def execute(self, *_args, **_kwargs):
        raise AssertionError("A fully migrated database must not execute DDL on startup.")


def test_existing_vin_guard_does_not_recreate_trigger():
    connection = _ExistingGuardDatabase()
    migrate_connection(connection)
    assert connection.probes == 1
