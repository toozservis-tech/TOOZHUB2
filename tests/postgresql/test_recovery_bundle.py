"""Real age + PostgreSQL roundtrip; synthetic source, private Unix-only restore."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from src.core import recovery_bundle as recovery
from src.core.file_erasure import FileErasure
from src.modules.vehicle_hub import models as m


class Objects:
    def __init__(self, paths):
        self.files = {path: ('SYNTHETIC PRIVATE FILE '+path).encode() for path in paths}
        self.files['admin_settings.json'] = b'{"synthetic":true}'
        self.reads = []

    def chunks(self, path):
        self.reads.append(path)
        if path not in self.files: raise recovery.RecoveryError('A required private object is unavailable')
        yield self.files[path]


@pytest.fixture
def age_key(tmp_path):
    age, keygen = shutil.which('age'), shutil.which('age-keygen')
    if not age or not keygen: pytest.skip('Official age binaries are required for encrypted recovery integration')
    identity = tmp_path/'recovery.key'
    subprocess.run([keygen, '-o', str(identity)], check=True, capture_output=True)
    identity.chmod(0o600)
    recipient = subprocess.run([keygen, '-y', str(identity)], check=True, capture_output=True).stdout.decode().strip()
    return age, identity, recipient


def seed(pg_db):
    key = 'tenant_1/vehicle_1/current.pdf'
    with pg_db.sessions() as db:
        tenant = m.Tenant(name='Synthetic recovery', license_key=uuid4().hex); db.add(tenant); db.flush()
        owner = m.Customer(tenant_id=tenant.id, email='recovery@example.invalid', role='user'); db.add(owner); db.flush()
        car = m.Vehicle(tenant_id=tenant.id, user_email=owner.email, nickname='Private fixture',
            photo_path='cover.jpg', orv_front_image_path='front.jpg'); db.add(car); db.flush()
        record = m.ServiceRecord(tenant_id=tenant.id, vehicle_id=car.id, description='Private synthetic repair',
            attachments=json.dumps([{'storage_key': key, 'path': key}]))
        db.add(record); db.flush()
        db.add(m.ServiceRecordAuditLog(tenant_id=tenant.id, vehicle_id=car.id, service_record_id=record.id,
            previous_snapshot_json=json.dumps({'attachments': [{'storage_key': 'tenant_1/vehicle_1/previous.pdf'}]})))
        db.add(m.VehicleAttachmentPrivacy(storage_key='tenant_1/vehicle_1/unattached.pdf', vehicle_id=car.id, owner_customer_id=owner.id))
        db.add(m.VehicleOwnershipArchive(vehicle_id=car.id, owner_customer_id=owner.id, period_key=uuid4().hex,
            profile_json=json.dumps({'photo_path':'old-cover.jpg','notes':'Original private owner'})))
        session = m.RepairPhotoSession(vehicle_id=car.id, service_id=owner.id, title='Synthetic repair', client_id=str(uuid4()))
        db.add(session); db.flush()
        db.add(m.RepairEvidencePhoto(session_id=session.id, author_id=owner.id, author_name='Synthetic', phase='before',
            source='library', file_path='repair.jpg', sha256='a'*64, mime_type='image/jpeg', size_bytes=7, client_id=str(uuid4())))
        db.add(m.ServiceDocumentIngestion(service_tenant_id=tenant.id, service_customer_id=owner.id,
            customer_id=owner.id, vehicle_id=car.id, stored_file_path='/legacy/data/service_workspace_docs/work.pdf'))
        db.add(FileErasure(path='private_repair_photos/deleted.jpg'))
        db.commit()
    paths = ['vehicle_photos/cover.jpg', 'vehicle_photos/old-cover.jpg', 'vehicle_orv_scans/front.jpg',
             'private_repair_photos/repair.jpg', 'service_workspace_docs/work.pdf',
             'service_record_attachments/'+key, 'service_record_attachments/tenant_1/vehicle_1/previous.pdf',
             'service_record_attachments/tenant_1/vehicle_1/unattached.pdf']
    return Objects(paths)


def capture(pg_db, age_key, objects, destination):
    age, identity, recipient = age_key
    binary = Path(__import__('os').environ['AUDIT_POSTGRES_BIN']).resolve()/'pg_dump'
    return recovery.create_bundle(destination, engine=pg_db.engine, schema='public', reader=objects,
        recipient=recipient, pg_dump=binary, age=age)


def test_encrypted_snapshot_restores_every_table_and_private_file(pg_db, age_key, tmp_path, monkeypatch):
    objects = seed(pg_db)
    # A write between collecting table hashes and pg_dump must not enter the dump.
    real_fingerprints = recovery.table_fingerprints
    def concurrent_write(connection, schema):
        result = real_fingerprints(connection, schema)
        with pg_db.sessions() as db:
            db.add(m.Tenant(name='Concurrent later row', license_key=uuid4().hex)); db.commit()
        return result
    monkeypatch.setattr(recovery, 'table_fingerprints', concurrent_write)
    bundle = tmp_path/'complete.zip.age'
    report = capture(pg_db, age_key, objects, bundle)
    assert report['private_files'] == 8 and not report['restore_ready']
    assert set(objects.reads) == set(objects.files)
    encrypted = bundle.read_bytes()
    for marker in [b'Private fixture', b'recovery@example.invalid', b'database.dump', b'current.pdf']:
        assert marker not in encrypted
    age, identity, _ = age_key
    with recovery.verified_bundle(bundle, identity=identity, expected_sha256=report['sha256'], age=age, parent=tmp_path) as (root, manifest):
        assert manifest['exclusions']['pending_erasures'] == 1
        for path, content in objects.files.items(): assert (root/'data'/path).read_bytes() == content
        restored_name = 'restore_'+uuid4().hex
        pg_db.cluster.run('createdb', '--template=template0', restored_name)
        pg_db.cluster.run('pg_restore', '--clean', '--if-exists', '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges',
            '--dbname', restored_name, root/'database.dump')
        engine = create_engine(pg_db.cluster.url(restored_name), hide_parameters=True)
        try:
            with engine.connect() as db:
                assert real_fingerprints(db, 'public') == manifest['tables']
                assert db.scalar(text('SELECT count(*) FROM tenants')) == 1
        finally: engine.dispose()
        temporary = root
    assert not temporary.exists(), 'Decrypted test material must not remain in a shared temporary directory'
    assert bundle.stat().st_mode & 0o077 == 0
    # Exercise the actual operator verification entry point too. It must create
    # its own database and must not accept an existing target URL.
    from scripts.verify_cloud_recovery import verify
    proof = verify(bundle, identity=identity, expected_sha256=report['sha256'],
                   binary=Path(__import__('os').environ['AUDIT_POSTGRES_BIN']), age=age)
    assert proof['isolated_restore_verified'] is True and proof['restore_ready'] is False
    assert proof['private_files'] == 8
    assert proof['tables'] == len(manifest['tables'])


def test_missing_object_aborts_instead_of_publishing_partial_backup(pg_db, age_key, tmp_path):
    objects = seed(pg_db); del objects.files['vehicle_photos/cover.jpg']
    destination = tmp_path/'missing.zip.age'
    with pytest.raises(recovery.RecoveryError, match='unavailable'):
        capture(pg_db, age_key, objects, destination)
    assert not destination.exists() and not list(tmp_path.glob('*.partial'))


def test_original_plain_text_annotations_remain_in_dump_without_becoming_file_paths(pg_db):
    objects = seed(pg_db)
    with pg_db.sessions() as db:
        record = db.query(m.ServiceRecord).first()
        record.attachments = 'Original paper receipt remains with its owner'
        db.commit()
    with pg_db.engine.connect() as db:
        paths, exclusions = recovery.private_inventory(db, 'public')
        assert 'service_record_attachments/tenant_1/vehicle_1/current.pdf' not in paths
        assert len(paths) == 7 and exclusions['pending_erasures'] == 1
        assert db.scalar(text('SELECT attachments FROM service_records')) == 'Original paper receipt remains with its owner'


def test_wrong_key_tampering_and_wrong_report_cannot_be_restored(pg_db, age_key, tmp_path):
    objects = seed(pg_db); bundle = tmp_path/'original.zip.age'
    report = capture(pg_db, age_key, objects, bundle)
    age, identity, _ = age_key
    with pytest.raises(recovery.RecoveryError, match='trusted'):
        with recovery.verified_bundle(bundle, identity=identity, expected_sha256='0'*64, age=age): pass
    other = tmp_path/'other.key'
    subprocess.run([shutil.which('age-keygen'), '-o', str(other)], check=True, capture_output=True); other.chmod(0o600)
    with pytest.raises(recovery.RecoveryError, match='authentication'):
        with recovery.verified_bundle(bundle, identity=other, expected_sha256=report['sha256'], age=age): pass
    changed = bytearray(bundle.read_bytes()); changed[-1] ^= 1
    bad = tmp_path/'modified.age'; bad.write_bytes(changed)
    with pytest.raises(recovery.RecoveryError, match='authentication'):
        with recovery.verified_bundle(bad, identity=identity, expected_sha256=hashlib.sha256(changed).hexdigest(), age=age): pass


def test_unhandled_new_file_column_fails_closed(pg_db):
    with pg_db.engine.begin() as db:
        db.execute(text('CREATE TABLE future_documents (id integer, private_path text)'))
        with pytest.raises(recovery.RecoveryError, match='handler'): recovery.private_inventory(db, 'public')


def test_fingerprints_do_not_depend_on_recovery_computer_locale(pg_db):
    with pg_db.engine.begin() as db:
        db.execute(text('CREATE TABLE locale_probe (happened_at timestamptz, duration interval, payload bytea, amount double precision)'))
        db.execute(text("INSERT INTO locale_probe VALUES ('2026-10-01 05:00:00+02', interval '2 days 4 hours', decode('ff000aff','hex'), 1.2345678901234567)"))
    with pg_db.engine.connect() as db:
        db.execute(text("SET LOCAL TimeZone = 'Europe/Prague'"))
        db.execute(text("SET LOCAL DateStyle = 'SQL, DMY'"))
        db.execute(text("SET LOCAL bytea_output = 'escape'"))
        first = recovery.table_fingerprints(db, 'public')
    with pg_db.engine.connect() as db:
        db.execute(text("SET LOCAL TimeZone = 'America/New_York'"))
        db.execute(text("SET LOCAL IntervalStyle = 'postgres_verbose'"))
        assert recovery.table_fingerprints(db, 'public') == first


@pytest.mark.parametrize('value', ['../other', '/absolute', 'a//b', 'a/./b', 'a\\b', 'https://outside.example/key', 'a\x00b'])
def test_invalid_references_never_become_storage_requests(value):
    with pytest.raises(recovery.RecoveryError): recovery.relative_file('vehicle_photos', value)


def test_storage_fetches_only_hashed_objects_and_never_follows_redirects():
    seen = []
    def transport(request):
        seen.append(request)
        return httpx.Response(302, headers={'location':'https://other.example/private'})
    reader = recovery.PrivateObjectReader('https://storage.example', 'synthetic-secret', transport=httpx.MockTransport(transport))
    try:
        with pytest.raises(recovery.RecoveryError): list(reader.chunks('vehicle_photos/cover.jpg'))
        assert len(seen) == 1
        assert seen[0].url.path.endswith('/assets/'+hashlib.sha256(b'vehicle_photos/cover.jpg').hexdigest())
    finally: reader.close()


def test_cloud_dump_cannot_fall_back_to_unencrypted_connection(monkeypatch):
    monkeypatch.setenv('PGOPTIONS', 'untrusted-inherited-options')
    plain = URL.create('postgresql+psycopg', host='db.example', database='synthetic')
    with pytest.raises(recovery.RecoveryError, match='encrypted'):
        recovery._pg_environment(plain)
    with pytest.raises(recovery.RecoveryError, match='encrypted'):
        recovery._pg_environment(plain.update_query_dict({'sslmode': 'prefer'}))
    env = recovery._pg_environment(plain.update_query_dict({'sslmode': 'verify-full'}))
    assert env['PGSSLMODE'] == 'verify-full' and 'PGOPTIONS' not in env
