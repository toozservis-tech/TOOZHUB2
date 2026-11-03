from io import BytesIO
import json
from PIL import Image
from PyPDF2 import PdfReader
import pytest
from fastapi import HTTPException
from test_vehicle_ownership_privacy import data, sharing, transfer, PRIVATE
from src.modules.vehicle_hub.service_job_models import ServiceJob, ServiceJobPhoto
from src.modules.vehicle_hub.vehicle_privacy import record_for_actor, require_attachment_private, require_attachment_write_period
from src.modules.vehicle_hub.record_presentation import work_note, display_summary
from src.modules.vehicle_hub.routers_v1 import service_records as api
from test_vehicle_history_report import vehicle, record, text_of
from src.modules.vehicle_hub.vehicle_history_report import build_vehicle_history_report
from uuid import uuid4


def publish_photo(s, name='repair.jpg', published=True):
    key=f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/{name}'
    from src.modules.vehicle_hub.models import VehicleOwnership
    ownership=s.db.query(VehicleOwnership).filter_by(vehicle_id=s.car.id,is_active=True).first()
    job=ServiceJob(tenant_id=s.car.tenant_id,ownership_id=ownership.id,ownership_started_at=ownership.owned_from or ownership.assigned_at,creation_hash="test",vehicle_id=s.car.id,service_id=s.service.id,owner_id=s.owner.id,
        title='Oprava',status='completed',final_record_id=s.record.id,client_id=str(uuid4()))
    s.db.add(job);s.db.flush()
    if not published:
        # Non-published private job cannot escape even if its record is corrupted into a link.
        job.status='in_progress'
    photo=ServiceJobPhoto(job_id=job.id,actor_id=s.service.id,sha256="test",storage_key=key,mime_type='image/jpeg',file_size=100,
        caption=PRIVATE,client_id=str(uuid4()))
    s.db.add(photo)
    items=json.loads(s.record.attachments);items.append({'storage_key':key,'file_name':name,'mime_type':'image/jpeg','caption':PRIVATE})
    s.record.attachments=json.dumps(items);s.db.commit()
    return key,job


def test_transfer_shares_only_published_repair_photos_not_price_invoice_or_caption(data):
    s=data;key,job=publish_photo(s);transfer(s)
    view=record_for_actor(s.db,s.record,s.buyer)
    assert view.price is None and view.note is None and view.user_id is None
    assert PRIVATE not in str(view.attachments)
    assert [x['storage_key'] for x in json.loads(view.attachments)]==[key]
    require_attachment_private(s.db,vehicle_id=s.car.id,key=key,actor=s.buyer)
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=s.car.id,key=s.key,actor=s.buyer)
    with pytest.raises(HTTPException):require_attachment_write_period(s.db,vehicle_id=s.car.id,key=key)
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=s.car.id+100,key=key,actor=s.buyer)
    assert record_for_actor(s.db,s.record,s.owner).price==917.25
    job.status='in_progress';s.db.commit()
    assert record_for_actor(s.db,s.record,s.buyer).attachments is None
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=s.car.id,key=key,actor=s.buyer)


def test_manual_image_invoice_is_not_a_public_repair_photo(data):
    s=data
    s.key=s.key.replace('.pdf','.jpg');s.record.attachments=json.dumps([{'storage_key':s.key,'file_name':'invoice.jpg','mime_type':'image/jpeg'}]);s.db.commit()
    transfer(s)
    assert record_for_actor(s.db,s.record,s.buyer).attachments is None
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=s.car.id,key=s.key,actor=s.buyer)


def test_notes_are_summarized_without_erasing_free_text():
    source='2026-10-25T22:40:08.030570 [received] Únik oleje\n2026-10-25T22:40:26 [received] Fotografie: Fotografie práce\n2026-10-25T22:47:05 [in_progress] Rozvody a spojka\nVlastní další řádek'
    assert work_note(source)=='Únik oleje\nRozvody a spojka\nVlastní další řádek'
    assert display_summary(record(description='Vše',note=source)).startswith('Únik oleje')
    assert work_note('Fotografie: moje vlastní poznámka')=='Fotografie: moje vlastní poznámka'


def test_four_small_previews_even_for_many_photos_and_no_price_for_new_owner():
    raw=BytesIO();Image.new('RGB',(480,360),'orange').save(raw,'JPEG')
    rows=[record(id=i,price=None,is_historical_summary=True,note=None) for i in range(4)]
    previews={i:{'images':[raw.getvalue()]*24,'total':24} for i in range(4)}
    pdf=build_vehicle_history_report(vehicle(),rows,[],photo_previews=previews)
    assert len(PdfReader(BytesIO(pdf)).pages)<=2
    text=text_of(pdf)
    assert text.count('Další fotografie v aplikaci Evidence Vozidel (20 dalších)')==4
    assert 'Kč' not in text and 'Částka' not in text and 'ZADANÉ NÁKLADY' not in text
    # Each record paints exactly four previews (ReportLab may deduplicate image objects).
    assert sum(page.get_contents().get_data().count(b' Do') for page in PdfReader(BytesIO(pdf)).pages)==17  # 16 images + logo


def test_pdf_uses_authorized_thumbnails_and_caps_record_at_four(data, monkeypatch):
    s=data;key,_=publish_photo(s);transfer(s)
    s.record.attachments=json.dumps(json.loads(s.record.attachments)*30);s.db.commit()
    calls=[]
    raw=BytesIO();Image.new('RGB',(480,360),'orange').save(raw,'JPEG')
    from fastapi.responses import Response
    def thumbnail(vehicle_id,key,current_user,db,thumbnail=False):
        require_attachment_private(db,vehicle_id=vehicle_id,key=key,actor=current_user)
        calls.append(key);assert thumbnail
        return Response(raw.getvalue())
    monkeypatch.setattr(api,'download_service_record_attachment',thumbnail)
    response=api.generate_service_records_pdf(s.car.id,s.buyer,s.db)
    assert calls==[key] and response.media_type=='application/pdf'
    assert PRIVATE not in text_of(response.body) and '917' not in text_of(response.body)
