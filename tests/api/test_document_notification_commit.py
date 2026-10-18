"""Document inbox entries represent committed record references, never uploads."""
import base64
from datetime import datetime
import json

from test_service_jobs import ctx
from test_service_http_lifecycle import http_flow
from src.modules.vehicle_hub.models import ServiceRecord
from src.modules.vehicle_hub.vehicle_privacy import register_attachment
from src.modules.vehicle_hub.routers_v1.vehicle_updates import list_updates


def inbox(db, owner):
    return list_updates(before_id=None, limit=100, current_user=owner, db=db)['items']


def make_record(ctx, attachments):
    db, owner, service, _, vehicle, *_ = ctx
    row = ServiceRecord(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        user_id=service.id, created_by_service_customer_id=service.id,
        performed_at=datetime.utcnow(), description='Document notification regression',
        attachments=json.dumps(attachments))
    db.add(row)
    return row


def test_draft_upload_and_rolled_back_record_never_publish_document(ctx):
    db, owner, service, _, vehicle, *_ = ctx
    key = f'tenant_{vehicle.tenant_id}/vehicle_{vehicle.id}/draft.pdf'
    register_attachment(db, vehicle_id=vehicle.id, key=key, actor=service)
    db.commit()
    assert inbox(db, owner) == []
    make_record(ctx, [{'storage_key': key}])
    db.flush()
    assert {row['event_type'] for row in inbox(db, owner)} == {'record.created', 'document.added'}
    db.rollback()
    assert inbox(db, owner) == []


def test_metadata_refresh_removal_and_owner_edit_do_not_add_document_alerts(ctx):
    db, owner, service, _, _, *_ = ctx
    record = make_record(ctx, [{'storage_key': 'original.pdf'}])
    db.commit()
    initial = len(inbox(db, owner))
    db.info['vehicle_update_actor_id'] = service.id
    record.attachments = json.dumps([{'storage_key': 'original.pdf', 'file_name': 'Renamed.pdf'}])
    db.commit()
    assert len(inbox(db, owner)) == initial
    record.attachments = '[]'
    db.commit()
    assert len(inbox(db, owner)) == initial
    db.info['vehicle_update_actor_id'] = owner.id
    record.attachments = json.dumps([{'storage_key': 'owner-upload.pdf'}])
    db.commit()
    assert len(inbox(db, owner)) == initial
    db.info['vehicle_update_actor_id'] = service.id
    record.attachments = json.dumps([{'storage_key': 'owner-upload.pdf'}, {'path': 'new-service.pdf'}])
    db.commit()
    newest = inbox(db, owner)[0]
    assert len(inbox(db, owner)) == initial + 1
    assert newest['event_type'] == 'document.added' and newest['record_id'] == record.id


def test_inline_parser_summary_is_not_a_document(ctx):
    db, owner, *_ = ctx
    make_record(ctx, [{'source_type': 'parsed_summary', 'description': 'Only metadata'}])
    db.commit()
    assert [item['event_type'] for item in inbox(db, owner)] == ['record.created']


def test_real_http_uploads_notify_only_after_saved_record_with_owner_downloads(http_flow, tmp_path, monkeypatch):
    from src.core import file_storage
    from src.modules.vehicle_hub.routers_v1 import service_records
    flow = http_flow
    monkeypatch.setattr(file_storage, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(file_storage, '_config', lambda: None)
    monkeypatch.setattr(service_records, 'SERVICE_RECORD_ATTACHMENTS_DIR', tmp_path / 'service_record_attachments')
    client, vehicle_id = flow.client, flow.vehicle_id
    headers = {}
    for name, actor in flow.actors.items():
        response = client.post('/user/login', json={'email': actor['email'], 'password': flow.password,
            'expected_role': actor['role']})
        assert response.status_code == 200
        headers[name] = {'Authorization': 'Bearer ' + response.json()['access_token']}
    owner, service, stranger = (headers[name] for name in ('owner', 'service', 'stranger'))
    request = client.post('/api/v1/services/workspace/access-requests', headers=service,
        json={'vehicle_id': vehicle_id, 'lookup_query': 'HTTP001', 'note': 'Upload test'})
    assert request.status_code == 200
    approved = client.put(f"/api/v1/services/access-requests/{request.json()['request_id']}",
        headers=owner, json={'decision': 'approved'})
    assert approved.status_code == 200
    updates_path = '/api/v1/vehicle-updates'
    baseline = client.get(updates_path, headers=owner).json()['items']
    attachments = []
    contents = [b'%PDF-1.4\nsynthetic invoice test\n%%EOF', b'synthetic photo fixture']
    records_path = f'/api/v1/vehicles/{vehicle_id}/records'
    for name, mime, content in zip(('test.pdf', 'test.jpg'), ('application/pdf', 'image/jpeg'), contents):
        upload = client.post(records_path + '/attachments/upload', headers=service, json={
            'file_name': name, 'file_mime_type': mime,
            'file_content_base64': base64.b64encode(content).decode()})
        assert upload.status_code == 200, upload.text
        attachments.append(upload.json())
        assert client.get(updates_path, headers=owner).json()['items'] == baseline
    payload = {'performed_at': '2026-10-18T10:48:00', 'category': 'SERVIS', 'description': 'Committed work and documents',
        'attachments': json.dumps(attachments)}
    rejected = client.post(records_path, headers=service, json={**payload, 'attachments': '[{"storage_key":"invalid"}]'})
    assert rejected.status_code in (403, 409, 422)
    assert client.get(updates_path, headers=owner).json()['items'] == baseline
    created = client.post(records_path, headers=service, json=payload)
    assert created.status_code == 200, created.text
    record_id = created.json()['id']
    updates = client.get(updates_path, headers=owner).json()['items']
    documents = [row for row in updates if row['event_type'] == 'document.added']
    assert len(documents) == 1
    assert documents[0]['record_id'] == record_id
    assert documents[0]['source_type'] == 'service_records' and documents[0]['source_id'] == record_id
    assert len(updates) == len(baseline) + 2
    detail = client.get(f'{records_path}/{record_id}', headers=owner)
    assert detail.status_code == 200
    assert len(json.loads(detail.json()['attachments'])) == 2
    for attachment, expected in zip(attachments, contents):
        downloaded = client.get(attachment['download_url'], headers=owner)
        assert downloaded.status_code == 200 and downloaded.content == expected
        assert client.get(attachment['download_url'], headers=stranger).status_code == 403
    assert client.get(updates_path, headers=stranger).json()['items'] == []
    assert client.get(updates_path, headers=service).json()['items'] == []
    assert flow.external_attempts == []
