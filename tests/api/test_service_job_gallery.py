"""Real upload bytes, compact previews and the same authorization as originals."""
import base64
import os
from io import BytesIO
from uuid import uuid4
import pytest
from PIL import Image
from fastapi import HTTPException
from test_service_jobs import ctx
from test_service_job_consent import pending, create, decide
from src.modules.vehicle_hub.routers_v1 import service_jobs as jobs
from src.modules.vehicle_hub.service_job_models import ServiceJobPhoto


def test_bounded_compression_preserves_orientation_strips_metadata():
    image = Image.frombytes('RGB', (2400, 1800), os.urandom(2400 * 1800 * 3))
    exif = Image.Exif(); exif[274] = 6; exif[315] = 'private author'
    original = BytesIO(); image.save(original, 'JPEG', quality=98, exif=exif)
    saved = jobs._compressed_job_image(original.getvalue())
    assert len(saved) <= 1_000_000
    assert len(saved) < len(original.getvalue()) / 2
    with Image.open(BytesIO(saved)) as result:
        assert result.height > result.width  # EXIF rotation applied, not dropped
        assert max(result.size) <= 2048
        assert result.getexif() == {}
        assert result.format == 'JPEG'
    thumb = jobs._compressed_job_image(saved, thumbnail=True)
    assert len(thumb) <= 100_000 and len(thumb) < len(saved)
    with Image.open(BytesIO(thumb)) as result:
        assert max(result.size) <= 480
        assert result.height > result.width


@pytest.mark.parametrize('consent', ['pending', 'rejected', 'approved'])
def test_thumbnail_authorization_and_original_unchanged(pending, consent):
    context, _ = pending
    db, owner, service, other, *_ = context
    job, _ = create(pending)
    if consent != 'pending': decide(pending, consent)
    image=Image.new('RGB',(1200,900),'orange');raw=BytesIO();image.save(raw,'PNG')
    payload=jobs.JobPhotoUpload(client_id=uuid4(),caption='Kontrola oleje',content_base64=base64.b64encode(raw.getvalue()).decode())
    reply=jobs.upload_service_job_photo(job['id'],payload,service,db);pid=reply['photo']['id']
    original=jobs.view_job_photo(job['id'],pid,service,db).body
    for actor in [service,owner,other]:
        if actor==service or (actor==owner and consent=='approved'):
            response=jobs.view_job_photo(job['id'],pid,actor,db,thumbnail=True)
            assert response.headers['cache-control']=='private, no-store'
            assert response.media_type=='image/jpeg'
            assert len(response.body)<len(original)
            with Image.open(BytesIO(response.body)) as thumb: assert max(thumb.size)==480
        else:
            with pytest.raises(HTTPException):jobs.view_job_photo(job['id'],pid,actor,db,thumbnail=True)
    assert jobs.view_job_photo(job['id'],pid,service,db).body==original
    assert db.query(ServiceJobPhoto).count()==1
    assert reply['photo']['file_size']==len(original)
