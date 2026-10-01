#!/usr/bin/env python3
"""Prove a captured copy in a disposable Unix-socket-only PostgreSQL cluster.

There is deliberately no database URL or restore target argument. Never starts
the application, sends mail, contacts storage or promotes the copy to service.
The capture report must come from a separately trusted location.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from src.core.recovery_bundle import RecoveryError, private_inventory, table_fingerprints, verified_bundle


@contextmanager
def private_cluster_directory():
    root = Path(tempfile.mkdtemp(prefix='sv-restore-', dir='/tmp'))
    root.chmod(0o700)
    try:
        yield root
    finally:
        # Never erase a cluster which failed to stop. The caller gets a failure
        # and its still-private working directory remains for operator recovery.
        if not (root/'cluster'/'postmaster.pid').exists():
            shutil.rmtree(root)


@contextmanager
def isolated_cluster(binary):
    binary = Path(binary).absolute()
    for name in ('initdb', 'pg_ctl', 'createdb', 'pg_restore'):
        if not (binary/name).is_file(): raise RecoveryError('PostgreSQL verification tools are incomplete')
    # A short path also fits macOS's Unix socket length limit.
    with private_cluster_directory() as root:
        socket = root/'socket'; socket.mkdir(mode=0o700)
        data = root/'cluster'
        password = secrets.token_urlsafe(48)
        pwfile = root/'password'; pwfile.write_text(password); pwfile.chmod(0o600)
        log = root/'postgres.log'; log.touch(mode=0o600)
        env = {'PATH': os.environ.get('PATH', ''), 'PGHOST': str(socket), 'PGPORT': '5432',
               'PGUSER': 'recovery_check', 'PGPASSWORD': password, 'PGCONNECT_TIMEOUT': '10'}

        def run(name, *args):
            result = subprocess.run([str(binary/name), *map(str, args)], env=env,
                                    capture_output=True, timeout=180)
            if result.returncode:
                # pg_restore diagnostics can contain private table values.
                raise RecoveryError('Isolated PostgreSQL '+name+' failed')

        engine = None
        try:
            run('initdb', '-D', data, '-U', 'recovery_check', '--pwfile', pwfile,
                '--auth-local=scram-sha-256', '--auth-host=reject', '--encoding=UTF8', '--locale=C')
            with (data/'postgresql.conf').open('a') as config:
                config.write("\nlisten_addresses = ''\n"
                    f"unix_socket_directories = '{socket}'\nunix_socket_permissions = 0700\n"
                    "max_connections = 10\nstatement_timeout = '60s'\nlock_timeout = '10s'\n"
                    "log_statement = 'none'\nlog_min_error_statement = 'panic'\n")
            run('pg_ctl', '-D', data, '-l', log, '-w', 'start')
            run('createdb', '--template=template0', 'recovery_copy')
            url = URL.create('postgresql+psycopg', username='recovery_check', password=password,
                             database='recovery_copy', query={'host': str(socket), 'port': '5432'})
            engine = create_engine(url, hide_parameters=True)
            with engine.connect() as db:
                if (db.scalar(text('SHOW listen_addresses')) != ''
                        or db.scalar(text('SELECT inet_server_addr()')) is not None
                        or db.scalar(text('SELECT current_database()')) != 'recovery_copy'):
                    raise RecoveryError('Recovery verification is not isolated')
            yield engine, run
        finally:
            if engine is not None: engine.dispose()
            if (data/'postmaster.pid').exists():
                run('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')


def verify(bundle, *, identity, expected_sha256, binary, age='age'):
    with verified_bundle(bundle, identity=identity, expected_sha256=expected_sha256, age=age) as (root, manifest):
        with isolated_cluster(binary) as (engine, run):
            # --clean applies exclusively to this newly created, private database.
            run('pg_restore', '--clean', '--if-exists', '--exit-on-error', '--single-transaction',
                '--no-owner', '--no-privileges', '--dbname', 'recovery_copy', root/'database.dump')
            with engine.connect() as db:
                db.execute(text('SET TRANSACTION READ ONLY'))
                restored = table_fingerprints(db, manifest['schema'])
                if restored != manifest.get('tables'):
                    raise RecoveryError('Restored tables do not match the captured snapshot')
                paths, exclusions = private_inventory(db, manifest['schema'])
                expected = {'database.dump', 'data/admin_settings.json'} | {'data/'+path for path in paths}
                if expected != set(manifest['files']) or exclusions != manifest.get('exclusions'):
                    raise RecoveryError('Restored file references do not match the captured objects')
        return {'sha256': expected_sha256, 'isolated_restore_verified': True, 'restore_ready': False,
                'tables': len(restored), 'rows': sum(v['rows'] for v in restored.values()),
                'private_files': len(paths), 'captured_at': manifest['created_at'],
                'verified_at': datetime.now(timezone.utc).isoformat(),
                'remaining_before_live_restore': manifest['restore_requires']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--identity-file', required=True)
    parser.add_argument('--trusted-report-file', required=True)
    parser.add_argument('--postgres-bin', required=True)
    parser.add_argument('--age', default='age')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report_path = Path(args.trusted_report_file)
        if report_path.is_symlink() or report_path.stat().st_mode & 0o077:
            raise RecoveryError('Trusted report must be private to its owner')
        report = json.loads(report_path.read_text())
        result = verify(args.bundle, identity=args.identity_file, expected_sha256=report['sha256'],
                        binary=args.postgres_bin, age=args.age)
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, RecoveryError) else
                          'Isolated verification failed; no production database was changed.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
