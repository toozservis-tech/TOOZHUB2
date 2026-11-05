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
             'vehicle_lifecycle_events', 'service_booking_requests', 'service_booking_request_events',
             'vehicle_update_inbox_states', 'vehicle_update_inbox_actions',
             'google_billing_identities', 'google_subscriptions', 'service_job_photos',
             'customer_home_garages', 'referral_codes', 'referrals', 'referral_rewards',
             'vehicle_transfer_invitations', 'admin_incidents', 'admin_incident_events', 'admin_incident_history',
             'admin_messages', 'admin_message_commands'}
    try:
        Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in added])
        with engine.begin() as connection:
            connection.execute(models.Tenant.__table__.insert().values(id=901, name='Retained tenant', license_key='synthetic-retained'))
        assert not added.intersection(inspect(engine).get_table_names())
        release.migrate(engine)
        from src.modules.vehicle_hub.admin_incident_models import AdminIncident, AdminIncidentEvent, AdminIncidentHistory
        with sessionmaker(bind=engine)() as db:
            admin=models.Customer(tenant_id=901,email='migration-admin@example.com',role='admin');db.add(admin);db.flush()
            event=models.SecurityAccessLog(user_email='migration-user@example.com',event_type='request_failed');db.add(event);db.flush()
            case=AdminIncident(source_event_id=event.id,actor_key=event.user_email,fingerprint='a'*64,created_by=admin.id);db.add(case);db.flush()
            db.add(AdminIncidentEvent(incident_id=case.id,event_id=event.id))
            db.add(AdminIncidentHistory(incident_id=case.id,admin_id=admin.id,action='note',status='open',version=1,note='Retained original support note'))
            from src.modules.vehicle_hub.admin_message_models import AdminMessage
            from datetime import datetime
            recipient=models.Customer(tenant_id=901,email='migration-recipient@example.com',role='user');db.add(recipient);db.flush()
            db.add(AdminMessage(recipient_id=recipient.id,sender_id=admin.id,sender_kind='admin',body='Retained private message',requires_ack=True,read_at=datetime(2026,11,5,12),acknowledged_at=datetime(2026,11,5,13)));db.commit()
        release.migrate(engine)
        with sessionmaker(bind=engine)() as db:
            assert db.query(models.SecurityAccessLog).count()==1
            assert db.query(AdminIncidentHistory).one().note=='Retained original support note'
            preserved=db.query(AdminMessage).one()
            assert preserved.body=='Retained private message' and preserved.acknowledged_at==datetime(2026,11,5,13)
        assert added.issubset(inspect(engine).get_table_names())
        with sessionmaker(bind=engine)() as db:
            assert db.get(models.Tenant, 901).name == 'Retained tenant'
            for module in ('service_jobs', 'vehicle_updates', 'vehicle_lifecycle', 'booking_requests', 'home_garages', 'referrals'):
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


def test_packaged_module_succeeds_in_fresh_python_process(tmp_path):
    """Do not import app/models in the child before its real -m entry point.

    Parent metadata only prepares an existing production-like DB. It cannot
    register a single SQLAlchemy table in either independent child process.
    """
    from pathlib import Path
    import os
    import shlex
    import shutil
    import subprocess
    import sys
    repo = Path(__file__).resolve().parents[2]
    image = tmp_path / 'image'
    image.mkdir()
    for line in (repo / 'Dockerfile.cloud').read_text().splitlines():
        if not line.startswith('COPY '):
            continue
        _, source, target = shlex.split(line)
        destination = image / target.removeprefix('./')
        if (repo / source).is_dir():
            shutil.copytree(repo / source, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.env*'))
        else:
            if target.endswith('/'):
                destination /= Path(source).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / source, destination)
    database_path = tmp_path / 'existing.sqlite'
    engine = create_engine(f'sqlite:///{database_path}')
    added = {'service_jobs', 'service_job_events', 'vehicle_updates', 'vehicle_update_receipts', 'vehicle_lifecycle_events',
             'vehicle_update_inbox_states', 'vehicle_update_inbox_actions',
             'google_billing_identities', 'google_subscriptions', 'service_job_photos',
             'customer_home_garages', 'referral_codes', 'referrals', 'referral_rewards',
             'vehicle_transfer_invitations', 'admin_incidents', 'admin_incident_events', 'admin_incident_history',
             'admin_messages', 'admin_message_commands'}
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in added])
    engine.dispose()
    env = os.environ.copy()
    env.update(DATABASE_URL=f'sqlite:///{database_path}', DATABASE_SCHEMA='',
               DATA_DIR_PATH=str(tmp_path / 'data'), PYTHONPATH=str(image), PYTHONDONTWRITEBYTECODE='1')
    for attempt in range(2):
        result = subprocess.run([sys.executable, '-m', 'scripts.migrate_mobile_release'],
            cwd=image, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, f'Fresh packaged process {attempt}: {result.stdout}\n{result.stderr}'
        assert 'Mobile release schema ready' in result.stdout
    with sessionmaker(bind=create_engine(f'sqlite:///{database_path}'))() as db:
        from src.server.admin_incidents import ready
        assert ready(db)
        assert inspect(db.connection()).has_table('vehicle_transfer_invitations')
        from src.server.admin_messages import ready as messages_ready
        assert messages_ready(db)
    # Verify 0015 also compiles its own FKs when invoked independently rather
    # than inheriting metadata loaded by 0014 in the orchestrator process.
    import sqlite3
    with sqlite3.connect(database_path) as connection:
        connection.execute('DROP TABLE vehicle_lifecycle_events')
    standalone = subprocess.run([sys.executable, '-m', 'scripts.migrate_vehicle_lifecycle'],
        cwd=image, env=env, capture_output=True, text=True, timeout=30)
    assert standalone.returncode == 0, standalone.stdout + standalone.stderr
    # Another fresh process independently inspects schema readiness, not the
    # parent process that prepared the old baseline.
    code = """
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.schema_management import module_schema_report
with sessionmaker(bind=engine)() as db:
    for module in ('service_jobs','vehicle_updates','vehicle_lifecycle'):
        assert module_schema_report(db,module)['available'],module
print('fresh readiness PASS')
"""
    result = subprocess.run([sys.executable, '-c', code], cwd=image, env=env,
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'fresh readiness PASS' in result.stdout
