"""Startup bursts must finish and retain their audit with the request pool full."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub import database, schema_management
from src.modules.vehicle_hub.models import SecurityAccessLog
from src.modules.licensing import apple_store
from src.server import security_tracking


def test_five_busy_requests_can_check_schema_and_persist_all_audits(pg_db, monkeypatch):
    url = pg_db.engine.url
    main = create_engine(url, pool_size=5, max_overflow=0, pool_timeout=0.25)
    monkeypatch.setattr(database, 'DB_URL', url.render_as_string(hide_password=False))
    monkeypatch.setattr(database, 'schema', '')
    audit = database._create_engine(pool_size=1, max_overflow=0)
    monkeypatch.setattr(security_tracking, 'SessionLocal', sessionmaker(bind=audit))
    monkeypatch.setattr(security_tracking, '_GEOLOOKUP_ENABLED', False)
    sessions = sessionmaker(bind=main)
    barrier = Barrier(5)

    def worker(number):
        with sessions() as db:
            db.execute(text('SELECT 1'))
            barrier.wait(timeout=5)
            # These checks used to request a sixth connection while all five
            # request connections were occupied, exactly like concurrent startup.
            schema_management.assert_module_ready(db, 'vehicles', detail_prefix='Vehicles')
            apple_store.require_schema(db)
            security_tracking.log_security_event(event_type='startup_pool_fixture',
                                                   details={'operation': number})
        return number

    try:
        with ThreadPoolExecutor(max_workers=5) as workers:
            assert sorted(workers.map(worker, range(5))) == list(range(5))
        with pg_db.sessions() as db:
            assert db.query(SecurityAccessLog).filter_by(event_type='startup_pool_fixture').count() == 5
        assert audit.pool.size() == 1
    finally:
        main.dispose(); audit.dispose()


def test_dedicated_pool_keeps_configured_schema(pg_db, monkeypatch):
    with pg_db.engine.begin() as conn:
        conn.execute(text('CREATE SCHEMA audit_fixture_scope'))
    monkeypatch.setattr(database, 'DB_URL', pg_db.engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(database, 'schema', 'audit_fixture_scope')
    audit = database._create_engine(pool_size=1, max_overflow=0)
    try:
        with audit.connect() as conn:
            assert conn.scalar(text('SELECT current_schema()')) == 'audit_fixture_scope'
    finally:
        audit.dispose()
