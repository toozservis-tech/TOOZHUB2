from src.core.file_storage import persist_file, cached_file
"""Authenticated repair documentation. No overwrite/delete endpoints or public file URLs."""
import base64
import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from src.core.config import DATA_DIR
from src.core.rbac import is_admin
from ..database import get_db
from ..models import Customer, RepairPhotoSession, RepairEvidencePhoto, Vehicle, VehicleRepairPrivacy
from ..ownership import user_owns_vehicle, lock_vehicle_access
from ..vehicle_privacy import may_read_repair_private
from ..service_access import require_service_vehicle_link
from .auth import get_current_user

router = APIRouter(prefix="/repair-documentation", tags=["repair-documentation"])
PHOTO_ROOT = DATA_DIR / "private_repair_photos"
MAX_BYTES = 12 * 1024 * 1024

class SessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    client_id: uuid.UUID

class PhotoCreate(BaseModel):
    phase: Literal["before", "during", "after"]
    note: str = Field(default="", max_length=2000)
    source: Literal["camera", "library"]
    captured_at: Optional[datetime] = None
    client_id: uuid.UUID
    file_content_base64: str = Field(max_length=17 * 1024 * 1024)

def vehicle_or_404(db, vehicle_id):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None: raise HTTPException(404, "Vozidlo nenalezeno.")
    return vehicle

def may_create(db, user, vehicle_id):
    if is_admin(user.role): return
    if user.role != "service": raise HTTPException(403, "Fotodokumentaci opravy vytváří servis.")
    require_service_vehicle_link(db, current_user=user, vehicle_id=vehicle_id, require_create_record=True)

def session_or_404(db, user, session_id, write=False):
    row = db.get(RepairPhotoSession, session_id)
    if row is None: raise HTTPException(404, "Oprava nenalezena.")
    vehicle = vehicle_or_404(db, row.vehicle_id)
    if is_admin(user.role): return row
    boundary = db.get(VehicleRepairPrivacy, row.id)
    if write:
        lock_vehicle_access(db, row.vehicle_id)
        # Re-read the boundary after a concurrent transfer has completed.
        boundary = db.get(VehicleRepairPrivacy, row.id, populate_existing=True)
        if boundary is not None: raise HTTPException(409, "Oprava patří k uzavřenému období vlastnictví. Založte novou opravu.")
        if row.service_id != user.id: raise HTTPException(403, "Tato dokumentace patří jinému servisu.")
        may_create(db, user, row.vehicle_id)
    elif row.service_id != user.id and not user_owns_vehicle(db, user, vehicle) and not (boundary and boundary.owner_customer_id == user.id):
        raise HTTPException(403, "K této dokumentaci nemáte přístup.")
    if not may_read_repair_private(db, row, user): raise HTTPException(403, "Dokumentace patří k předchozímu vlastnictví vozidla.")
    return row

def session_out(row):
    return {"id": row.id, "vehicle_id": row.vehicle_id, "service_id": row.service_id, "title": row.title, "created_at": row.created_at}

def photo_out(row):
    return {key: getattr(row, key) for key in ["id", "session_id", "author_id", "author_name", "phase", "note", "source", "captured_at", "uploaded_at", "sha256", "size_bytes", "mime_type"]}

@router.get("/vehicles/{vehicle_id}")
def sessions(vehicle_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    vehicle = vehicle_or_404(db, vehicle_id)
    query = db.query(RepairPhotoSession).filter_by(vehicle_id=vehicle_id)
    if not is_admin(user.role) and not user_owns_vehicle(db, user, vehicle):
        if user.role != "service": raise HTTPException(403, "K vozidlu nemáte přístup.")
        # A service keeps access to its own photographs, even after sharing is revoked.
        query = query.filter_by(service_id=user.id)
    return [session_out(row) for row in query.order_by(RepairPhotoSession.created_at.desc(), RepairPhotoSession.id.desc()).all()
            if may_read_repair_private(db, row, user)]

@router.post("/vehicles/{vehicle_id}")
def create_session(vehicle_id: int, payload: SessionCreate, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_vehicle_access(db, vehicle_id)
    vehicle_or_404(db, vehicle_id); may_create(db, user, vehicle_id)
    title = payload.title.strip()
    if not title: raise HTTPException(422, "Vyplňte název opravy.")
    existing = db.query(RepairPhotoSession).filter_by(service_id=user.id, client_id=str(payload.client_id)).first()
    if existing:
        if existing.vehicle_id != vehicle_id or existing.title != title: raise HTTPException(409, "Identifikátor opravy už byl použit.")
        return session_out(existing)
    row = RepairPhotoSession(vehicle_id=vehicle_id, service_id=user.id, title=title, client_id=str(payload.client_id))
    db.add(row)
    try: db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Oprava se již ukládá. Načtěte seznam a zkuste to znovu.")
    db.refresh(row); return session_out(row)

@router.get("/sessions/{session_id}/photos")
def photos(session_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    session_or_404(db, user, session_id)
    return [photo_out(row) for row in db.query(RepairEvidencePhoto).filter_by(session_id=session_id).order_by(RepairEvidencePhoto.uploaded_at, RepairEvidencePhoto.id).all()]

@router.post("/sessions/{session_id}/photos")
def upload(session_id: int, payload: PhotoCreate, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    session_or_404(db, user, session_id, write=True)
    try: content = base64.b64decode(payload.file_content_base64, validate=True)
    except Exception: raise HTTPException(422, "Neplatná data fotografie.")
    if not content or len(content) > MAX_BYTES: raise HTTPException(413, "Fotografie musí mít nejvýše 12 MB.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ["JPEG", "PNG"]: raise HTTPException(415, "Podporujeme JPEG a PNG.")
            if image.width * image.height > 32_000_000: raise HTTPException(413, "Fotografie má příliš vysoké rozlišení.")
            mime = "image/jpeg" if image.format == "JPEG" else "image/png"
            image.verify()
    except HTTPException: raise
    except Exception: raise HTTPException(422, "Fotografii nelze přečíst.")
    captured = payload.captured_at
    if captured and captured.tzinfo:
        captured = captured.astimezone(timezone.utc).replace(tzinfo=None)
    digest = hashlib.sha256(content).hexdigest()
    existing = db.query(RepairEvidencePhoto).filter_by(session_id=session_id, client_id=str(payload.client_id)).first()
    if existing:
        if (existing.sha256, existing.phase, existing.note, existing.source, existing.captured_at) != (digest, payload.phase, payload.note.strip(), payload.source, captured):
            raise HTTPException(409, "Identifikátor fotografie už byl použit pro jiný obsah.")
        return photo_out(existing)
    PHOTO_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = uuid.uuid4().hex + (".jpg" if mime == "image/jpeg" else ".png")
    target = PHOTO_ROOT / name
    row = RepairEvidencePhoto(session_id=session_id, author_id=user.id, author_name=user.name or user.email, phase=payload.phase, note=payload.note.strip(), source=payload.source, captured_at=captured, sha256=digest, file_path=name, mime_type=mime, size_bytes=len(content), client_id=str(payload.client_id))
    try:
        persist_file(target, content)
        target.chmod(0o600)
        db.add(row); db.flush(); response = photo_out(row); db.commit()
    except Exception:
        db.rollback(); target.unlink(missing_ok=True)
        raise HTTPException(409, "Fotografie se neuložila. Zkuste odeslání zopakovat.")
    return response

@router.get("/photos/{photo_id}/file")
def photo_file(photo_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RepairEvidencePhoto, photo_id)
    if row is None: raise HTTPException(404, "Fotografie nenalezena.")
    session_or_404(db, user, row.session_id)
    target = (PHOTO_ROOT / row.file_path).resolve()
    if target.parent != PHOTO_ROOT.resolve(): raise HTTPException(404, "Soubor fotografie není dostupný.")
    cached_file(target)
    if not target.is_file(): raise HTTPException(404, "Soubor fotografie není dostupný.")
    if hashlib.sha256(target.read_bytes()).hexdigest() != row.sha256: raise HTTPException(409, "Kontrola integrity fotografie selhala.")
    return FileResponse(target, media_type=row.mime_type, filename=f"oprava_{row.session_id}_{row.phase}_{row.id}{target.suffix}", headers={"Cache-Control": "private, no-store"})

@router.get('/sessions/{session_id}/report.pdf')
def repair_report(session_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    from fastapi.responses import Response
    from ..repair_report import build_repair_report, MAX_REPORT_PHOTOS

    session = session_or_404(db, user, session_id)
    vehicle = vehicle_or_404(db, session.vehicle_id)
    evidence = db.query(RepairEvidencePhoto).filter_by(session_id=session_id).order_by(
        RepairEvidencePhoto.uploaded_at, RepairEvidencePhoto.id
    ).limit(MAX_REPORT_PHOTOS + 1).all()
    document = build_repair_report(session, vehicle, evidence, PHOTO_ROOT)
    return Response(document, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="protokol-opravy-{session_id}.pdf"',
        'Cache-Control': 'private, no-store',
    })
