"""Explicit pre-deploy entry point for the shared mobile API schema.

Invoked by deployment tooling only; never imported by application startup.
Each additive migration owns its transaction and is safe to retry.
"""
from scripts.migrate_service_updates import migrate as migrate_updates
from scripts.migrate_vehicle_lifecycle import migrate as migrate_lifecycle


def migrate(bind=None):
    migrate_updates(bind)
    migrate_lifecycle(bind)


if __name__ == '__main__':
    migrate()
    print('Mobile release schema ready: service jobs, vehicle updates and owner lifecycle. Existing data retained.')
