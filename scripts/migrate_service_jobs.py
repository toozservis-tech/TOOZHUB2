"""Compatibility entry point: jobs and their transactional inbox migrate together."""
from scripts.migrate_service_updates import migrate


if __name__ == '__main__':
    migrate()
    print('Service jobs and vehicle inbox ready; existing history retained.')
