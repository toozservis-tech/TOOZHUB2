"""Bounded metadata checks without caching permissions or hiding broken schemas."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from src.modules.vehicle_hub import schema_management as schema


@pytest.fixture
def database(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'schema.sqlite'),
                           pool_size=1, max_overflow=0, pool_timeout=0.1)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE performance_fixture (id INTEGER PRIMARY KEY)'))
    with patch.dict(schema.MODULE_REQUIREMENTS, {
        'performance_fixture': {'tables': {'performance_fixture'},
                                'columns': {'performance_fixture': {'id'}}},
    }):
        yield engine
    engine.dispose()


def ready(db):
    schema.assert_module_ready(db, 'performance_fixture', detail_prefix='Fixture unavailable')


def test_warm_check_uses_no_sql_and_cold_check_uses_existing_connection(database):
    statements = []
    event.listen(database, 'before_cursor_execute', lambda *args: statements.append(args[2]))
    with Session(database) as db:
        # Hold the sole connection: a second checkout would time out.
        db.execute(text('SELECT 1'))
        ready(db)
        assert statements
    statements.clear()
    with Session(database) as db:
        ready(db)
    assert statements == []


def test_expiry_detects_schema_damage_and_admin_report_is_always_fresh(database):
    with patch.object(schema, 'monotonic', return_value=100):
        with Session(database) as db:
            ready(db)
    with database.begin() as conn:
        conn.execute(text('DROP TABLE performance_fixture'))
    with Session(database) as db:
        assert not schema.module_schema_report(db, 'performance_fixture')['available']
    with patch.object(schema, 'monotonic', return_value=161):
        with Session(database) as db, pytest.raises(HTTPException) as error:
            ready(db)
        assert error.value.status_code == 503


def test_success_does_not_transfer_to_another_database(database, tmp_path):
    with Session(database) as db:
        ready(db)
    other = create_engine('sqlite:///' + str(tmp_path / 'other.sqlite'))
    try:
        with Session(other) as db, pytest.raises(HTTPException):
            ready(db)
    finally:
        other.dispose()


def test_failed_check_is_retried_after_migration(database):
    with database.begin() as conn:
        conn.execute(text('DROP TABLE performance_fixture'))
    with Session(database) as db, pytest.raises(HTTPException):
        ready(db)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE performance_fixture (id INTEGER PRIMARY KEY)'))
    with Session(database) as db:
        ready(db)


def test_new_required_column_cannot_reuse_old_success(database):
    with Session(database) as db:
        ready(db)
    schema.MODULE_REQUIREMENTS['performance_fixture']['columns']['performance_fixture'].add('new_column')
    with Session(database) as db, pytest.raises(HTTPException):
        ready(db)
