"""Opt-in, private local PostgreSQL cluster. Cannot target an existing database.

Run: AUDIT_POSTGRES_BIN=/path/to/pg/bin python -m pytest tests/postgresql -q
No DATABASE_URL is accepted: every run initializes a new Unix-only cluster.
The cluster, dumps and synthetic files are retained in the reported /tmp folder.
"""
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

# Module imports cannot accidentally select an inherited production endpoint.
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['DATABASE_SCHEMA'] = ''
os.environ['SUPABASE_URL'] = ''
os.environ['SUPABASE_SECRET_KEY'] = ''

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub import models  # register application tables
from src.core.session_revocation import RevokedAccessToken


@pytest.fixture(scope='session')
def pg_cluster():
    raw_bin = os.environ.get('AUDIT_POSTGRES_BIN')
    if not raw_bin:
        pytest.skip('Set AUDIT_POSTGRES_BIN to run isolated PostgreSQL integration tests')
    binary = Path(raw_bin).resolve()
    for name in ['initdb', 'pg_ctl', 'pg_dump', 'pg_restore', 'createdb']:
        if not (binary / name).is_file():
            pytest.fail(f'Missing PostgreSQL executable: {name}')
    root = Path(tempfile.mkdtemp(prefix='sv-pg-', dir='/tmp'))
    root.chmod(0o700)
    socket_dir = root / 'socket'; socket_dir.mkdir(mode=0o700)
    data = root / 'cluster'
    password = secrets.token_urlsafe(32)
    pwfile = root / 'password'; pwfile.write_text(password); pwfile.chmod(0o600)
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update({'PGPASSWORD': password, 'PGHOST': str(socket_dir), 'PGPORT': '5432', 'PGUSER': 'audit_owner'})

    def run(name, *args):
        result = subprocess.run([str(binary / name), *map(str,args)], env=env, capture_output=True, timeout=60)
        if result.returncode:
            # Commands only handle generated fixture data. Credentials are never command arguments.
            pytest.fail(f'{name} failed: {result.stderr.decode(errors="replace")[-1500:]}')
        return result.stdout.decode(errors='replace')

    run('initdb', '-D', data, '-U', 'audit_owner', '--pwfile', pwfile,
        '--auth-local=scram-sha-256', '--auth-host=scram-sha-256', '--encoding=UTF8', '--locale=C')
    with (data / 'postgresql.conf').open('a') as config:
        config.write(f"\nlisten_addresses = ''\nunix_socket_directories = '{socket_dir}'\n"
            "unix_socket_permissions = 0700\nmax_connections = 30\n"
            "statement_timeout = '15s'\nlock_timeout = '10s'\nlog_statement = 'none'\n")
    run('pg_ctl', '-D', data, '-l', root / 'postgres.log', '-w', 'start')
    def url(database):
        return URL.create('postgresql+psycopg', username='audit_owner', password=password,
            database=database, query={'host': str(socket_dir), 'port': '5432'})
    try:
        yield SimpleNamespace(root=root, run=run, url=url)
    finally:
        run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')
        print(f'\nSynthetic PostgreSQL audit artifacts retained: {root}')


@pytest.fixture
def pg_db(pg_cluster):
    name = 'fixture_' + uuid4().hex
    pg_cluster.run('createdb', '--template=template0', name)
    engine = create_engine(pg_cluster.url(name), pool_size=8, max_overflow=4, hide_parameters=True)
    with engine.connect() as connection:
        assert connection.scalar(text('SHOW listen_addresses')) == ''
        assert connection.scalar(text('SELECT current_database()')) == name
        assert connection.scalar(text('SELECT inet_server_addr()')) is None
    Base.metadata.create_all(engine)
    try:
        yield SimpleNamespace(engine=engine, sessions=sessionmaker(bind=engine, autoflush=False),
            name=name, cluster=pg_cluster)
    finally:
        engine.dispose()
