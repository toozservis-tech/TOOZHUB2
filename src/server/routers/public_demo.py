"""Email-gated, read-only showcase. Never issues a customer credential."""
from datetime import datetime, timedelta
import hashlib
import hmac
import secrets
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, String, Integer, DateTime, update, delete, case
from src.core.config import JWT_SECRET_KEY
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import render_email_layout, render_panel
from src.server.routers.user_auth import _limit_auth

router = APIRouter(prefix="/public-demo", tags=["Public demo"])
_KEY = hmac.new(JWT_SECRET_KEY.encode(), b"public-demo-only-v1", hashlib.sha256).digest()

class DemoChallenge(Base):
    __tablename__ = "public_demo_challenges"
    id = Column(String(64), primary_key=True)
    email_hash = Column(String(64), nullable=False, index=True)
    digest = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    consumed = Column(Integer, nullable=False, default=0)

# Separate from short-lived challenges: never expose the OTP or its digest.
DEMO_HISTORY_DAYS = 90

class DemoAccess(Base):
    __tablename__ = "public_demo_access"
    id = Column(Integer, primary_key=True)
    challenge_hash = Column(String(64), nullable=False, unique=True)
    email = Column(String(320), nullable=False, index=True)
    requested_at = Column(DateTime, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime)
    verified_at = Column(DateTime)
    status = Column(String(24), nullable=False, default="sending")
    attempts = Column(Integer, nullable=False, default=0)


def prune_demo_history(db, now=None):
    db.execute(delete(DemoAccess).where(DemoAccess.requested_at < (now or datetime.utcnow())-timedelta(days=DEMO_HISTORY_DAYS)))


def demo_access_list(db, search="", status="all", limit=50, offset=0):
    ensure_schema(db)
    now = datetime.utcnow()
    prune_demo_history(db, now)
    db.commit()
    state = case((DemoAccess.status.in_(["sent", "sending"]) & (DemoAccess.expires_at <= now), "expired"), else_=DemoAccess.status)
    query = db.query(DemoAccess, state.label("state"))
    if search.strip():
        query = query.filter(DemoAccess.email.contains(search.strip().lower(), autoescape=True))
    if status != "all":
        query = query.filter(state == status)
    total = query.count()
    rows = query.order_by(DemoAccess.requested_at.desc(), DemoAccess.id.desc()).offset(offset).limit(limit).all()
    def stamp(value):
        return value.isoformat(timespec="seconds") + "Z" if value else None
    return {"total": total, "retention_days": DEMO_HISTORY_DAYS, "items": [
        {"id": row.id, "email": row.email, "requested_at": stamp(row.requested_at),
         "sent_at": stamp(row.sent_at), "verified_at": stamp(row.verified_at),
         "status": state, "attempts": row.attempts} for row, state in rows]}

class SendCode(BaseModel):
    email: EmailStr

class VerifyCode(BaseModel):
    challenge_id: str = Field(min_length=20, max_length=64)
    code: str = Field(pattern=r"^\d{6}$")

def _digest(value):
    return hmac.new(_KEY, value.encode(), hashlib.sha256).hexdigest()

def ensure_schema(db):
    DemoChallenge.__table__.create(db.get_bind(), checkfirst=True)
    DemoAccess.__table__.create(db.get_bind(), checkfirst=True)

@router.post("/request-code")
def request_code(payload: SendCode, request: Request, response: Response, db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    email = str(payload.email).strip().lower()
    _limit_auth(request, "public-demo-send", email, calls=3, period=900)
    service = EmailService()
    if not service.is_configured():
        raise HTTPException(503, "Odesílání kódu není nyní dostupné. Zkuste to později.")
    ensure_schema(db)
    now = datetime.utcnow()
    eh = _digest(email)
    recent = db.query(DemoChallenge).filter(DemoChallenge.email_hash == eh,
        DemoChallenge.created_at > now-timedelta(minutes=15)).count()
    if recent >= 3:
        raise HTTPException(429, "Další kód můžete vyžádat za 15 minut.")
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = secrets.token_urlsafe(24)
    db.execute(delete(DemoChallenge).where(DemoChallenge.expires_at < now-timedelta(days=1)))
    db.execute(update(DemoChallenge).where(DemoChallenge.email_hash == eh).values(consumed=1))
    prune_demo_history(db, now)
    db.execute(update(DemoAccess).where(DemoAccess.email == email,
        DemoAccess.status.in_(["sent", "sending"])).values(status="superseded"))
    db.add(DemoAccess(challenge_hash=_digest("audit:"+challenge), email=email,
        requested_at=now, expires_at=now+timedelta(minutes=10), status="sending", attempts=0))
    row = DemoChallenge(id=challenge, email_hash=eh, digest=_digest(challenge+":"+code),
        created_at=now, expires_at=now+timedelta(minutes=10), attempts=0, consumed=0)
    db.add(row)
    db.commit()
    body = (f"Váš jednorázový kód pro ukázku Evidence Vozidel: {code}\n\n"
        "Platí 10 minut a lze jej použít pouze jednou. Zadejte jej v aplikaci, kde jste o něj požádali. "
        "Demo obsahuje pouze smyšlená data a neumožňuje úpravy ani nákupy. "
        "Nevytváří placený účet ani předplatné. Pokud jste kód nevyžádali, e-mail ignorujte.")
    html = render_email_layout(title="Váš vstup do ukázky Evidence Vozidel",
        subtitle="Jednorázové ověření e-mailu", intro="Zadejte tento kód v aplikaci:",
        panels=[render_panel(title="Ověřovací kód", message=code),
                render_panel(title="Co se stane po ověření", message="Otevře se ukázka pouze pro prohlížení. Kód platí 10 minut a pouze jednou. Nevznikne předplatné ani placený účet.")],
        accent="#f59e0b", footer_note="Pokud jste kód nevyžádali, tento e-mail ignorujte. Kód nikomu nesdělujte.")
    try:
        sent = service.send_simple_email(to=email, subject="Evidence Vozidel – ověřovací kód do ukázky", body=body, html_body=html)
        if sent is not True:
            raise RuntimeError("mail not accepted")
    except Exception:
        db.execute(update(DemoChallenge).where(DemoChallenge.id==challenge).values(consumed=1))
        db.execute(update(DemoAccess).where(DemoAccess.challenge_hash==_digest("audit:"+challenge)).values(status="delivery_failed"))
        db.commit()
        raise HTTPException(503, "Kód se nepodařilo odeslat. Zkuste to později.") from None
    db.execute(update(DemoAccess).where(DemoAccess.challenge_hash==_digest("audit:"+challenge)).values(
        sent_at=datetime.utcnow(), status=case((DemoAccess.status == "sending", "sent"), else_=DemoAccess.status)))
    db.commit()
    return {"challenge_id": challenge, "message": "Kód jsme odeslali. Platí 10 minut."}

@router.post("/verify-code")
def verify_code(payload: VerifyCode, request: Request, response: Response, db=Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    _limit_auth(request, "public-demo-verify", calls=10, period=900)
    ensure_schema(db)
    now = datetime.utcnow()
    # Atomic attempt accounting and single-use redemption also cover concurrent requests.
    allowed = (DemoChallenge.id==payload.challenge_id, DemoChallenge.consumed==0,
        DemoChallenge.attempts<5, DemoChallenge.expires_at>now)
    changed = db.execute(update(DemoChallenge).where(*allowed).values(attempts=DemoChallenge.attempts+1)).rowcount
    if changed:
        db.execute(update(DemoAccess).where(DemoAccess.challenge_hash==_digest("audit:"+payload.challenge_id)).values(attempts=DemoAccess.attempts+1))
    db.commit()
    row = db.get(DemoChallenge, payload.challenge_id)
    if not changed or not row or not hmac.compare_digest(row.digest, _digest(payload.challenge_id+":"+payload.code)):
        if changed and row and row.attempts >= 5:
            db.execute(update(DemoAccess).where(DemoAccess.challenge_hash==_digest("audit:"+payload.challenge_id),
                DemoAccess.status=="sent").values(status="locked"))
            db.commit()
        raise HTTPException(400, "Kód není platný, vypršel nebo byl použit. Vyžádejte nový kód.")
    used = db.execute(update(DemoChallenge).where(DemoChallenge.id==payload.challenge_id,
        DemoChallenge.consumed==0, DemoChallenge.expires_at>now).values(consumed=1)).rowcount
    if used == 1:
        db.execute(update(DemoAccess).where(DemoAccess.challenge_hash==_digest("audit:"+payload.challenge_id)).values(
            status="verified", verified_at=now))
    db.commit()
    if used != 1:
        raise HTTPException(400, "Kód již byl použit. Vyžádejte nový kód.")
    token = jwt.encode({"aud":"public-demo", "scope":"demo:read", "iat":now,
        "exp":now+timedelta(hours=2), "jti":secrets.token_urlsafe(24)}, _KEY, algorithm="HS256")
    return {"access_token":token, "expires_in":7200}

@router.get("/content")
def content(response: Response, credentials: HTTPAuthorizationCredentials=Depends(HTTPBearer())):
    response.headers["Cache-Control"] = "no-store"
    try:
        claims = jwt.decode(credentials.credentials, _KEY, algorithms=["HS256"], audience="public-demo", options={"require":["exp","aud","scope"]})
        if claims["scope"] != "demo:read": raise ValueError()
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Ukázka vypršela. Vyžádejte si nový kód.") from None
    return {"title":"Ukázková garáž", "vehicles":[
        {"id":1,"name":"Škoda Octavia", "year":"2021", "engine":"2.0 TDI · 110 kW", "mileage":"84 250 km", "image":"DemoOctavia",
         "records":["12. 9. 2026 · Výměna oleje a filtrů · 4 200 Kč", "18. 4. 2026 · Přední brzdy · 6 800 Kč"],
         "reminders":["Technická kontrola · 20. 11. 2026", "Výměna pneumatik · 1. 11. 2026"]},
        {"id":2,"name":"Volkswagen Golf", "year":"2023", "engine":"Benzín · automat", "mileage":"32 600 km", "image":"DemoGolf",
         "records":["3. 8. 2026 · Pravidelná prohlídka · 5 500 Kč"],
         "reminders":["Roční servis · 3. 8. 2027"]}],
        "reservations":["22. 10. 2026 v 9:00 · Přezutí pneumatik · Ukázkový servis · Potvrzeno"],
        "costs":["Servis celkem · 16 500 Kč", "Škoda Octavia · 11 000 Kč", "Volkswagen Golf · 5 500 Kč"]}
