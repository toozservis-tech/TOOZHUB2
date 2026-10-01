"""Read-only, encrypted PostgreSQL + private object recovery material.

No application import, database write, bucket listing, mail or production restore.
An exported snapshot binds the dump and file inventory. Missing committed files
abort the bundle. New file keys are immutable in the application. Concurrent
erasure may cause a retry, never a silently incomplete successful copy.

This is the capture/verification primitive, not an automatic backup scheduler.
Restoring an older copy to service additionally requires a current erasure
journal, session invalidation, key recovery and payment reconciliation.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from threading import Timer
from uuid import uuid4
import zipfile

import httpx
from sqlalchemy import inspect, text

FORMAT = 'spravavozidel-recovery-v1'
CHUNK = 1024 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
DIRECTORIES = frozenset(('vehicle_photos', 'vehicle_orv_scans', 'private_repair_photos',
                         'service_record_attachments', 'service_workspace_docs'))


class RecoveryError(RuntimeError):
    """Messages deliberately contain no credentials, paths, SQL or customer data."""


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_]*', value):
        raise RecoveryError('Unsupported database identifier')
    return '"'+value+'"'


def relative_file(directory, value):
    if directory not in DIRECTORIES or not isinstance(value, str):
        raise RecoveryError('Invalid private file reference')
    if directory == 'service_workspace_docs' and value.startswith('/') and directory in PurePosixPath(value).parts:
        value = PurePosixPath(value).name  # Existing legacy document layout only.
    parts = value.split('/')
    if (not value or len(value) > 1000 or '\\' in value or ':' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(p in ('', '.', '..') for p in parts)):
        raise RecoveryError('Invalid private file reference')
    return directory+'/'+value


def _json(value, expected):
    try:
        result = json.loads(value) if isinstance(value, (str, bytes)) else value
    except (TypeError, ValueError):
        raise RecoveryError('Invalid document inventory') from None
    if not isinstance(result, expected):
        raise RecoveryError('Invalid document inventory')
    return result


def private_inventory(connection, schema):
    """Exact live references; never infer authority by walking a cache/bucket."""
    quoted = identifier(schema)
    tables = set(inspect(connection).get_table_names(schema=schema))
    covered = {
        'vehicles': {'photo_path', 'orv_front_image_path', 'orv_back_image_path'},
        'repair_evidence_photos': {'file_path'},
        'service_document_ingestions': {'stored_file_path'},
        'vehicle_orv_scans': {'front_image_path', 'back_image_path'},
        'private_file_erasure_queue': {'path'},
    }
    for table in tables:
        for column in inspect(connection).get_columns(table, schema=schema):
            if (column['name'] == 'path' or column['name'].endswith('_path')) and column['name'] not in covered.get(table, set()):
                raise RecoveryError('A private file field has no recovery inventory handler')
    paths, omitted = set(), set()

    def rows(table, columns):
        if table not in tables:
            return []
        names = ','.join(identifier(c) for c in columns)
        return connection.execute(text(f'SELECT {names} FROM {quoted}.{identifier(table)}')).mappings()

    def add(directory, value):
        if value is not None and value != '': paths.add(relative_file(directory, value))

    def profile(value):
        add('vehicle_photos', value.get('photo_path'))
        for field in ('orv_front_image_path', 'orv_back_image_path'):
            add('vehicle_orv_scans', value.get(field))

    def attachments(value):
        if value is None or value == '': return
        if isinstance(value, str):
            try: value = json.loads(value)
            except ValueError:
                # Original app allowed plain-text attachment annotations. They
                # remain in the DB dump but do not identify a managed object.
                if not value.lstrip().startswith(('[', '{')): return
                raise RecoveryError('Invalid attachment inventory') from None
        for item in _json(value, list):
            if not isinstance(item, dict): raise RecoveryError('Invalid attachment inventory')
            for field in ('storage_key', 'path'):
                if item.get(field): add('service_record_attachments', item[field])

    for row in rows('vehicles', ('photo_path', 'orv_front_image_path', 'orv_back_image_path')): profile(row)
    for row in rows('vehicle_ownership_archives', ('profile_json',)): profile(_json(row['profile_json'], dict))
    for row in rows('repair_evidence_photos', ('file_path',)): add('private_repair_photos', row['file_path'])
    for row in rows('service_document_ingestions', ('stored_file_path',)): add('service_workspace_docs', row['stored_file_path'])
    for row in rows('service_records', ('attachments',)): attachments(row['attachments'])
    for row in rows('service_record_audit_logs', ('previous_snapshot_json', 'new_snapshot_json')):
        for value in row.values():
            if value: attachments(_json(value, dict).get('attachments'))
    for row in rows('vehicle_attachment_privacy', ('storage_key', 'owner_customer_id', 'author_customer_id')):
        if row['owner_customer_id'] is not None or row['author_customer_id'] is not None:
            add('service_record_attachments', row['storage_key'])
    for row in rows('vehicle_orv_scans', ('front_image_path', 'back_image_path', 'status', 'vehicle_id')):
        for field in ('front_image_path', 'back_image_path'):
            value = row[field]
            if not value: continue
            key = relative_file('vehicle_orv_scans', value)
            if row['status'] == 'processing' and row['vehicle_id'] is None: omitted.add(key)
            else: paths.add(key)
    erasures = set()
    for row in rows('private_file_erasure_queue', ('path',)):
        directory, separator, value = str(row['path']).partition('/')
        if not separator: raise RecoveryError('Invalid erasure inventory')
        erasures.add(relative_file(directory, value))
    # A committed privacy tombstone takes precedence over an old file mapping.
    paths -= erasures
    return sorted(paths), {'pending_uploads': len(omitted-paths), 'pending_erasures': len(erasures)}


def table_fingerprints(connection, schema):
    quoted = identifier(schema)
    fingerprints = {}
    # A restore on a computer with another time zone/locale must compare equal.
    connection.execute(text("SELECT set_config('TimeZone', 'UTC', true), "
        "set_config('DateStyle', 'ISO, YMD', true), "
        "set_config('IntervalStyle', 'iso_8601', true), "
        "set_config('bytea_output', 'hex', true), "
        "set_config('extra_float_digits', '3', true)"))
    for table in sorted(inspect(connection).get_table_names(schema=schema)):
        digest, count = hashlib.sha256(), 0
        # PostgreSQL canonical JSON avoids driver-specific datetime/decimal repr.
        result = connection.execution_options(stream_results=True).execute(text(
            f'SELECT to_jsonb(t)::text AS row FROM {quoted}.{identifier(table)} t '
            'ORDER BY (to_jsonb(t)::text) COLLATE "C"'))
        for (row,) in result:
            digest.update(row.encode('utf-8')+b'\n'); count += 1
        result.close()
        fingerprints[table] = {'rows': count, 'sha256': digest.hexdigest()}
    # Do not leave server-side cursors enabled for subsequent transaction commands.
    connection.execution_options(stream_results=False)
    return fingerprints


class PrivateObjectReader:
    def __init__(self, base_url, secret, bucket='toozhub-private', *, transport=None):
        from urllib.parse import urlsplit
        url = urlsplit(base_url)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ('', '/') or not secret
                or not re.fullmatch('[a-zA-Z0-9_-]+', bucket)):
            raise RecoveryError('Incomplete private storage configuration')
        self.base = base_url.rstrip('/')+'/storage/v1/object/'+bucket+'/'
        self.client = httpx.Client(headers={'apikey': secret}, timeout=45, follow_redirects=False, transport=transport)

    def chunks(self, relative):
        # Reference cannot turn into an arbitrary URL, even with corrupt metadata.
        key = 'assets/'+hashlib.sha256(relative.encode('utf-8')).hexdigest()
        try:
            with self.client.stream('GET', self.base+key) as response:
                if response.status_code != 200: raise RecoveryError('A required private object is unavailable')
                yield from response.iter_bytes(CHUNK)
        except httpx.HTTPError:
            raise RecoveryError('Private storage read failed') from None

    def close(self): self.client.close()


def digest_file(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _pg_environment(url):
    query = dict(url.query)
    host = query.get('host') or url.host
    if not host or not url.database: raise RecoveryError('Incomplete database configuration')
    if not str(host).startswith('/') and query.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
        raise RecoveryError('Cloud recovery requires encrypted database transport')
    # Do not inherit another cluster, service, password file or arbitrary PGOPTIONS.
    result = {'PATH': os.environ.get('PATH', ''), 'PGCONNECT_TIMEOUT': '15',
              'PGHOST': str(host), 'PGPORT': str(query.get('port') or url.port or 5432),
              'PGDATABASE': url.database, 'PGUSER': url.username or '', 'PGPASSWORD': url.password or ''}
    for key in ('sslmode', 'sslrootcert', 'sslcert', 'sslkey'):
        if key in query: result['PG'+key.upper()] = str(query[key])
    return result


@contextmanager
def _process(command, **kwargs):
    process = subprocess.Popen(command, stderr=subprocess.DEVNULL, **kwargs)
    timer = Timer(600, process.kill); timer.daemon = True; timer.start()
    try:
        yield process
    finally:
        timer.cancel()
        if process.poll() is None: process.kill()
        process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None: stream.close()


def create_bundle(destination, *, engine, schema, reader, recipient, pg_dump='pg_dump', age='age'):
    """Source connection is read-only. Only a complete encrypted bundle is published."""
    identifier(schema)
    if engine.dialect.name != 'postgresql' or not re.fullmatch('age1[a-z0-9]{58}', recipient):
        raise RecoveryError('PostgreSQL and a recovery public key are required')
    database_environment = _pg_environment(engine.url)  # Validate TLS before opening any connection.
    destination = Path(destination)
    if destination.exists(): raise RecoveryError('Recovery destination already exists')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    partial = destination.parent/('.recovery-'+uuid4().hex+'.partial')
    manifest = {'format': FORMAT, 'created_at': datetime.now(timezone.utc).isoformat(), 'schema': schema,
                'restore_requires': ['current_erasure_reconciliation', 'session_invalidation',
                    'server_secret_recovery', 'payment_reconciliation'], 'files': {}}
    total = 0
    try:
        with partial.open('xb') as target:
            partial.chmod(0o600)
            with _process([str(age), '--encrypt', '--recipient', recipient], stdin=subprocess.PIPE, stdout=target) as encryptor:
                with zipfile.ZipFile(encryptor.stdin, mode='w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    def write_member(name, chunks, limit=MAX_FILE_BYTES):
                        nonlocal total
                        digest, size = hashlib.sha256(), 0
                        with archive.open(name, 'w', force_zip64=True) as member:
                            for chunk in chunks:
                                size += len(chunk); total += len(chunk)
                                if size > limit or total > MAX_BUNDLE_BYTES: raise RecoveryError('Recovery size limit exceeded')
                                digest.update(chunk); member.write(chunk)
                        manifest['files'][name] = {'bytes': size, 'sha256': digest.hexdigest()}
                    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as db:
                        db.execute(text('SET TRANSACTION READ ONLY'))
                        snapshot = db.scalar(text('SELECT pg_export_snapshot()'))
                        paths, manifest['exclusions'] = private_inventory(db, schema)
                        manifest['tables'] = table_fingerprints(db, schema)
                        manifest['postgresql_version'] = db.scalar(text('SHOW server_version_num'))
                        command = [str(pg_dump), '--format=custom', '--no-owner', '--no-privileges',
                                   '--strict-names', '--schema='+schema, '--snapshot='+snapshot,
                                   '--lock-wait-timeout=30000', '--no-password']
                        with _process(command, stdout=subprocess.PIPE, env=database_environment) as dump:
                            write_member('database.dump', iter(lambda: dump.stdout.read(CHUNK), b''), MAX_BUNDLE_BYTES)
                            if dump.wait(timeout=10) != 0: raise RecoveryError('Database capture failed')
                        for relative in paths:
                            write_member('data/'+relative, reader.chunks(relative))
                        # Durable mutable settings are captured separately, never mistaken for env secrets.
                        write_member('data/admin_settings.json', reader.chunks('admin_settings.json'))
                        manifest['settings_captured_at'] = datetime.now(timezone.utc).isoformat()
                        db.rollback()
                    archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode())
                encryptor.stdin.close()
                if encryptor.wait(timeout=30) != 0: raise RecoveryError('Recovery encryption failed')
            target.flush(); os.fsync(target.fileno())
        # link is atomic and refuses to replace another backup, including a racing writer.
        os.link(partial, destination)
        return {'format': FORMAT, 'sha256': digest_file(destination), 'encrypted_bytes': destination.stat().st_size,
                'tables': len(manifest['tables']), 'private_files': len(manifest['files'])-2,
                'created_at': manifest['created_at'], 'restore_ready': False}
    except (OSError, subprocess.SubprocessError, zipfile.BadZipFile):
        raise RecoveryError('Recovery capture failed') from None
    finally:
        partial.unlink(missing_ok=True)


@contextmanager
def verified_bundle(bundle, *, identity, expected_sha256, age='age', parent=None):
    """Authenticate and verify in a newly-created private directory; never restore DB.

    The expected digest MUST come from the separately protected capture report,
    not from inside the received bundle. age encryption alone does not identify
    the sender: anyone knowing the public recipient can create another bundle.
    """
    if not re.fullmatch('[a-f0-9]{64}', expected_sha256) or digest_file(bundle) != expected_sha256:
        raise RecoveryError('Recovery file does not match the trusted capture report')
    identity = Path(identity)
    if identity.is_symlink() or identity.stat().st_mode & 0o077:
        raise RecoveryError('Recovery key permissions are not private')
    with tempfile.TemporaryDirectory(prefix='sv-recovery-', dir=parent) as raw:
        root = Path(raw); root.chmod(0o700)
        plaintext = root/'bundle.zip'
        with plaintext.open('xb') as target:
            plaintext.chmod(0o600)
            with _process([str(age), '--decrypt', '--identity', str(identity), str(bundle)], stdout=subprocess.PIPE) as decryptor:
                size = 0
                for chunk in iter(lambda: decryptor.stdout.read(CHUNK), b''):
                    size += len(chunk)
                    if size > MAX_BUNDLE_BYTES: raise RecoveryError('Recovery size limit exceeded')
                    target.write(chunk)
                if decryptor.wait(timeout=30) != 0: raise RecoveryError('Recovery authentication failed')
        try:
            with zipfile.ZipFile(plaintext) as archive:
                info = archive.getinfo('manifest.json')
                if info.file_size > 5*CHUNK: raise RecoveryError('Recovery manifest is too large')
                manifest = _json(archive.read(info), dict)
                if manifest.get('format') != FORMAT: raise RecoveryError('Unsupported recovery format')
                identifier(manifest.get('schema'))
                files = manifest.get('files')
                if not isinstance(files, dict) or 'database.dump' not in files: raise RecoveryError('Incomplete recovery manifest')
                names = archive.namelist()
                if len(names) != len(set(names)) or set(names) != set(files)|{'manifest.json'}:
                    raise RecoveryError('Unexpected recovery archive member')
                total = 0
                for name, expected in files.items():
                    if name not in ('database.dump', 'data/admin_settings.json'):
                        parts = name.split('/', 2)
                        if len(parts) != 3 or parts[0] != 'data' or 'data/'+relative_file(parts[1], parts[2]) != name:
                            raise RecoveryError('Invalid recovery archive member')
                    member = archive.getinfo(name)
                    if not isinstance(expected, dict) or member.file_size != expected.get('bytes'):
                        raise RecoveryError('Recovery file size mismatch')
                    total += member.file_size
                    if total > MAX_BUNDLE_BYTES: raise RecoveryError('Recovery size limit exceeded')
                    target = root/name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(member) as source, target.open('xb') as output:
                        target.chmod(0o600)
                        for chunk in iter(lambda: source.read(CHUNK), b''):
                            digest.update(chunk); output.write(chunk)
                    if digest.hexdigest() != expected.get('sha256'): raise RecoveryError('Recovery file checksum mismatch')
        except (ValueError, KeyError, OSError, zipfile.BadZipFile):
            raise RecoveryError('Invalid recovery bundle') from None
        yield root, manifest
