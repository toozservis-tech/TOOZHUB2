"""Administrator oversight must not depend on a customer/service relationship."""
import base64
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from PyPDF2 import PdfWriter

from test_service_jobs import ctx
from test_service_job_consent import pending, create, decide
from src.core.mfa import verified_claims
from src.core.security import create_access_token
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings, Tenant
from src.modules.vehicle_hub.routers_v1 import service_jobs as jobs


@pytest.fixture(params=['admin', 'developer_admin'])
def admin(ctx, request):
    db = ctx[0]
    tenant = Tenant(name='Separate administrative account', license_key=str(uuid4()))
    db.add(tenant); db.flush()
    actor = Customer(tenant_id=tenant.id, email='admin-oversight@example.test',
                     role=request.param, password_hash='isolated-test')
    db.add(actor); db.commit()
    return actor


def test_admin_reads_unrelated_private_and_rejected_jobs_without_publishing(pending, admin):
    context, request = pending
    db, owner, service, _, vehicle, *_ = context
    job, _ = create(pending)
    for rejected in (False, True):
        if rejected: decide(pending, 'rejected')
        assert jobs.list_jobs(vehicle.id, admin, db)['items'][0]['id'] == job['id']
        assert jobs.list_jobs(vehicle.id, admin, db, request.id)['items'][0]['id'] == job['id']
        detail = jobs.get_job(job['id'], admin, db)
        assert detail['shared_with_owner'] is False
        assert detail['consent_status'] == ('rejected' if rejected else 'pending')
        assert jobs.list_jobs(vehicle.id, owner, db)['items'] == []
    with pytest.raises(HTTPException) as error:
        jobs.update_job(job['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=1,
                        message='Do not impersonate the workshop'), admin, db)
    assert error.value.status_code == 403
    assert jobs.get_job(job['id'], service, db)['version'] == 1


def test_admin_reads_published_jobs_after_transfer_and_without_current_owner(pending, admin):
    context, _ = pending
    db, _, _, other, vehicle, assignment, _ = context
    job, _ = create(pending); decide(pending)
    assignment.customer_id = other.id
    assignment.owned_from = datetime.utcnow() + timedelta(days=1)
    db.commit()
    assert jobs.get_job(job['id'], admin, db)['id'] == job['id']
    assert len(jobs.list_jobs(vehicle.id, admin, db)['items']) == 1
    assignment.is_active = False; db.commit()
    assert len(jobs.list_jobs(vehicle.id, admin, db)['items']) == 1
    with pytest.raises(HTTPException) as error:
        jobs.list_jobs(999999, admin, db)
    assert error.value.status_code == 404


def test_admin_can_open_job_photos_and_pdf_but_disabled_accounts_cannot(pending, admin):
    context, _ = pending
    db, owner, service, _, vehicle, *_ = context
    job, _ = create(pending)
    data = BytesIO(); Image.new('RGB', (20, 20), 'blue').save(data, 'JPEG')
    photo = jobs.upload_service_job_photo(job['id'], jobs.JobPhotoUpload(client_id=uuid4(),
        content_base64=base64.b64encode(data.getvalue()).decode()), service, db)['photo']
    data = BytesIO(); pdf = PdfWriter(); pdf.add_blank_page(width=100, height=100); pdf.write(data)
    document = jobs.upload_job_document(job['id'], jobs.JobDocumentUpload(client_id=uuid4(),
        file_name='Evidence.pdf', content_base64=base64.b64encode(data.getvalue()).decode()), service, db)['documents'][0]
    assert jobs.view_job_photo(job['id'], photo['id'], admin, db).media_type == 'image/jpeg'
    assert jobs.view_job_photo(job['id'], photo['id'], admin, db, thumbnail=True).media_type == 'image/jpeg'
    response = jobs.view_job_document(job['id'], document['id'], admin, db)
    assert response.media_type == 'application/pdf'
    assert Path(response.path).read_bytes() == data.getvalue()
    with pytest.raises(HTTPException): jobs.view_job_document(job['id'], document['id'], owner, db)
    for flag in ('is_disabled', 'is_deleted'):
        setattr(admin, flag, True); db.commit()
        for read in (lambda: jobs.list_jobs(vehicle.id, admin, db),
                     lambda: jobs.get_job(job['id'], admin, db),
                     lambda: jobs.view_job_photo(job['id'], photo['id'], admin, db),
                     lambda: jobs.view_job_photo(job['id'], photo['id'], admin, db, thumbnail=True),
                     lambda: jobs.view_job_document(job['id'], document['id'], admin, db)):
            with pytest.raises(HTTPException) as error: read()
            assert error.value.status_code == 403
        setattr(admin, flag, False); db.commit()


def test_admin_request_filter_cannot_return_another_vehicle(pending, admin):
    context, request = pending
    db, _, _, _, vehicle, *_ = context
    create(pending)
    with pytest.raises(HTTPException) as error:
        jobs.list_jobs(vehicle.id, admin, db, request.id + 999)
    assert error.value.status_code == 404


def test_real_http_auth_still_requires_verified_admin_session(pending, admin, monkeypatch):
    context, _ = pending
    db, owner, _, _, vehicle, *_ = context
    job, _ = create(pending)
    app = FastAPI(); app.include_router(jobs.router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    from src.modules.vehicle_hub.routers_v1 import auth
    monkeypatch.setattr(auth, 'log_user_activity', lambda **kw: None)
    with TestClient(app) as client:
        paths = [f'/api/v1/vehicles/{vehicle.id}/service-jobs', f'/api/v1/service-jobs/{job["id"]}']
        token = create_access_token({'sub': admin.email, 'sv': 0})
        for path in paths:
            response = client.get(path, headers={'Authorization': f'Bearer {token}'})
            assert response.status_code == 403
            assert response.headers['X-Admin-Verification'] == 'required'
        db.add(CustomerSecuritySettings(tenant_id=admin.tenant_id, customer_id=admin.id, two_factor_enabled=True,
                                        totp_secret='JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'))
        db.commit()
        verified = create_access_token(verified_claims(admin))
        for path in paths:
            response = client.get(path, headers={'Authorization': f'Bearer {verified}'})
            assert response.status_code == 200, response.text
        owner_token = create_access_token({'sub': owner.email, 'sv': 0})
        assert client.get(paths[1], headers={'Authorization': f'Bearer {owner_token}'}).status_code == 403
