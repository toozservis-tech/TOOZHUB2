"""The deploy command upgrades an existing isolated schema, not runtime startup."""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub import models
from src.modules.vehicle_hub.schema_management import module_schema_report
from scripts import migrate_mobile_release as release


def test_mobile_release_upgrades_existing_baseline_and_is_repeatable(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/mobile-release.sqlite')
    added = {'service_jobs', 'service_job_events', 'vehicle_updates', 'vehicle_update_receipts',
             'vehicle_lifecycle_events'}
    try:
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in added])
        with engine.begin() as connection:
            connection.execute(models.Tenant.__table__.insert().values(id=901, name='Retained tenant', license_key='synthetic-retained'))
        assert not added.intersection(inspect(engine).get_table_names())
        release.migrate(engine)
        release.migrate(engine)
        assert added.issubset(inspect(engine).get_table_names())
        with sessionmaker(bind=engine)() as db:
            assert db.get(models.Tenant, 901).name == 'Retained tenant'
            for module in ('service_jobs', 'vehicle_updates', 'vehicle_lifecycle'):
                assert module_schema_report(db, module)['available']
    finally:
        engine.dispose()


def test_release_does_not_attempt_lifecycle_after_service_update_failure(monkeypatch):
    calls = []
    def fail(bind):
        calls.append('updates')
        raise RuntimeError('isolated migration failure')
    monkeypatch.setattr(release, 'migrate_updates', fail)
    monkeypatch.setattr(release, 'migrate_lifecycle', lambda bind: calls.append('lifecycle'))
    import pytest
    with pytest.raises(RuntimeError):
        release.migrate(object())
    assert calls == ['updates']
