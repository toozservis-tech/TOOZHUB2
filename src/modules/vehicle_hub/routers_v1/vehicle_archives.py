"""Read-only originals from an owner's completed vehicle ownership period."""
import json
import mimetypes
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.core.file_storage import cached_file
from src.core.rbac import is_admin
from ..database import get_db
from ..models import (Customer, VehicleOwnershipArchive, VehicleRecordPrivacy,
    VehicleAttachmentPrivacy, VehicleRepairPrivacy, ServiceRecord, RepairPhotoSession)
from .auth import get_current_user
from .schemas import ServiceRecordOutV1

router = APIRouter(prefix='/vehicle-archives', tags=['vehicle-archives'])


def owned_archive(db, actor, archive_id):
    row = db.get(VehicleOwnershipArchive, archive_id)
    if row is None or (row.owner_customer_id != actor.id and not is_admin(actor.role)):
        raise HTTPException(404, 'Archiv vlastnictví nebyl nalezen.')
    return row


def archive_out(row):
    profile = json.loads(row.profile_json)
    return {'id': row.id, 'vehicle_id': row.vehicle_id, 'created_at': row.created_at,
            'nickname': profile.get('nickname') or 'Vozidlo', 'plate': profile.get('plate'),
            'vin': profile.get('vin')}


@router.get('')
def list_archives(user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    # This is the personal archive, including for administrators.
    rows = db.query(VehicleOwnershipArchive).filter_by(owner_customer_id=user.id).order_by(VehicleOwnershipArchive.created_at.desc()).all()
    return [archive_out(row) for row in rows]


@router.get('/{archive_id}')
def archive_detail(archive_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    row = owned_archive(db, user, archive_id)
    records = db.query(ServiceRecord).join(VehicleRecordPrivacy,
        VehicleRecordPrivacy.record_id == ServiceRecord.id).filter(VehicleRecordPrivacy.archive_id == row.id).order_by(ServiceRecord.performed_at.desc()).all()
    repairs = db.query(RepairPhotoSession).join(VehicleRepairPrivacy,
        VehicleRepairPrivacy.session_id == RepairPhotoSession.id).filter(VehicleRepairPrivacy.archive_id == row.id).all()
    return {**archive_out(row), 'profile': json.loads(row.profile_json),
            'records': [ServiceRecordOutV1.model_validate(record, from_attributes=True) for record in records],
            'repairs': [{'id': repair.id, 'vehicle_id': repair.vehicle_id, 'service_id': repair.service_id, 'title': repair.title, 'created_at': repair.created_at} for repair in repairs]}


def private_file(path):
    if path is None:
        raise HTTPException(404, 'Soubor nebyl nalezen.')
    cached_file(path)
    if not path.is_file():
        raise HTTPException(404, 'Soubor nebyl nalezen.')
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
        filename=path.name, headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/{archive_id}/attachment')
def archive_attachment(archive_id: int, key: str = Query(..., min_length=3, max_length=500),
                       user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    row = owned_archive(db, user, archive_id)
    reference = db.get(VehicleAttachmentPrivacy, key)
    if reference is None or reference.archive_id != row.id or reference.vehicle_id != row.vehicle_id:
        raise HTTPException(404, 'Příloha v tomto archivu nebyla nalezena.')
    from .service_records import _attachment_path_for_vehicle
    return private_file(_attachment_path_for_vehicle(key, vehicle_id=row.vehicle_id))


@router.get('/{archive_id}/image/{kind}')
def archive_image(archive_id: int, kind: Literal['cover', 'registration-front', 'registration-back'],
                  user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    row = owned_archive(db, user, archive_id)
    from .vehicles import VEHICLE_PHOTOS_DIR
    from ..orv_scans import ORV_SCANS_DIR
    field, root = {'cover': ('photo_path', VEHICLE_PHOTOS_DIR),
        'registration-front': ('orv_front_image_path', ORV_SCANS_DIR),
        'registration-back': ('orv_back_image_path', ORV_SCANS_DIR)}[kind]
    key = json.loads(row.profile_json).get(field)
    if not isinstance(key, str) or not key:
        raise HTTPException(404, 'Obrázek v tomto archivu nebyl nalezen.')
    root = root.resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise HTTPException(404, 'Obrázek v tomto archivu nebyl nalezen.')
    return private_file(path)
