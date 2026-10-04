"""Native billing reads the original licensing data; never returns gateway secrets."""
import json
import hashlib
from typing import Literal
from uuid import UUID

from src.core.branding import APP_DISPLAY_NAME

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request as InternalRequest

from ..database import get_db
from ..models import Customer, LicensePaymentTransaction, Tenant
from .auth import get_current_user
from . import license_status as billing
from ...licensing.service import PLAN_FEATURES, PLAN_LIMITS

router = APIRouter(prefix="/mobile")
CONTRACT_VERSION = "SV-COMGATE-2026-09-29"
DOCUMENTS = [
    ("Obchodní podmínky", "obchodni-podminky.html"),
    ("Platební podmínky", "platebni-podminky.html"),
    ("Reklamace a vrácení peněz", "reklamacni-rad.html"),
    ("Ochrana osobních údajů", "ochrana-osobnich-udaju.html"),
]
SELLER = dict(name="ToozServis Auto/Pneu Tomáš Zachurčok", company_id="87854716",
              address="Gorkého 2351/19a, 568 02 Svitavy, Česká republika",
              email="info@toozservis.cz", phone="+420731552299")
FEATURES = {
    "manual_service_records_enabled": "Ruční servisní úkony (Zdarma: 2 u vozidla)",
    "reminders_enabled": "Připomínky termínů", "ares_enabled": "Vyhledání firmy v ARES",
    "vehicle_history_enabled": "Servisní historie", "documents_enabled": "Dokumenty k vozidlu",
    "costs_tracking_enabled": "Evidence nákladů", "statistics_enabled": "Statistiky",
    "sharing_with_service_enabled": "Sdílení se servisem", "vin_decode_enabled": "Načítání VIN, ORV a STK",
}


class Selection(BaseModel):
    plan: Literal["basic", "premium"]
    billing_period: Literal["monthly", "yearly"] = "monthly"


class Purchase(Selection):
    request_id: UUID
    expected_amount_halers: int
    expected_currency: str
    expected_test_mode: bool
    expected_recurring: bool | None = None
    contract_version: str
    accept_terms: bool
    accept_immediate_service: bool
    accept_recurring: bool


def _tenant(user):
    if not user.tenant_id:
        raise HTTPException(403, "Účet nemá přiřazenou organizaci.")
    return user.tenant_id


def _quote(payload, user, db):
    cfg = billing._load_comgate_config()
    subscription = billing._get_subscription(db, _tenant(user))
    if subscription and subscription.provider == "apple" and (
        subscription.auto_renew_enabled or
        (subscription.current_period_end and subscription.current_period_end > billing._utcnow())
    ):
        raise HTTPException(409, "Účet má předplatné přes Apple. Spravujte ho v App Storu.")
    if (subscription and subscription.init_recurring_id and subscription.current_period_end
        and subscription.current_period_end > billing._utcnow()
        and subscription.status in {"active", "cancel_at_period_end", "grace"}):
        raise HTTPException(409, "Máte aktivní předplatné. Použijte změnu tarifu od dalšího období nebo obnovení prodlužování.")
    amount = billing._price_for_plan(cfg, payload.plan, payload.billing_period)
    period = payload.billing_period
    if subscription and subscription.status == "legacy_manual":
        quote = billing._build_legacy_checkout_quote(cfg=cfg, subscription=subscription,
                  target_plan=payload.plan, billing_period=period)
        amount = quote["charge_amount_halers"]
        period = quote["billing_period"]
    return dict(plan=payload.plan, billing_period=period, amount_halers=amount,
                renewal_amount_halers=billing._price_for_plan(cfg, payload.plan, period),
                currency=cfg["currency"], test_mode=cfg["test_mode"], contract_version=CONTRACT_VERSION,
                recurring=not (subscription and subscription.status == "legacy_manual"))


@router.get("/catalog")
def catalog(request: Request, current_user: Customer = Depends(get_current_user)):
    cfg = billing._load_comgate_config()
    base = billing._request_backend_public_url(request)
    return dict(app_name=APP_DISPLAY_NAME, enabled=cfg["configured"], test_mode=cfg["test_mode"],
        currency=cfg["currency"], contract_version=CONTRACT_VERSION, seller=SELLER,
        delivery="Digitální služba bez dopravy. Tarif se aktivuje po potvrzení úhrady.",
        documents=[dict(title=title, url=f"{base}/web/{filename}") for title, filename in DOCUMENTS],
        gateway_logo_url=f"{base}/web/assets/comgate-logo-horizontal-red.png",
        gateway_support_email="podpora@comgate.cz", gateway_support_phone="+420228224267",
        plans=[dict(id=plan, title={"free":"Zdarma", "basic":"Basic", "premium":"Premium"}[plan],
                    vehicles_limit=PLAN_LIMITS[plan],
                    features=[title for key,title in FEATURES.items() if PLAN_FEATURES[plan].get(key)],
                    monthly=0 if plan=="free" else cfg["plans"][plan]["monthly"],
                    yearly=0 if plan=="free" else cfg["plans"][plan]["yearly"])
               for plan in ["free", "basic", "premium"]])


@router.post("/quote")
def quote(payload: Selection, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    return _quote(payload, current_user, db)


@router.post("/checkout")
def checkout(payload: Purchase, request: Request, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.contract_version != CONTRACT_VERSION:
        raise HTTPException(409, "Podmínky se změnily. Načtěte objednávku znovu.")
    if payload.expected_recurring is None:
        raise HTTPException(409, "Aktualizujte aplikaci a načtěte objednávku znovu.")
    if not all([payload.accept_terms, payload.accept_immediate_service]):
        raise HTTPException(400, "Před objednáním potvrďte podmínky a souhlasy.")
    # Serialise reservations by tenant; commit before contacting the gateway.
    tenant_id = _tenant(current_user)
    db.query(Tenant).filter(Tenant.id == tenant_id).with_for_update().one()
    request_id = str(payload.request_id)
    ref = billing._build_comgate_ref_id(tenant_id, payload.plan, payload.billing_period)[:9]
    ref += billing._base36_encode(int.from_bytes(hashlib.sha256(request_id.encode()).digest()[:8], "big") % (36 ** 8)).zfill(8)
    prior = db.query(LicensePaymentTransaction).filter(LicensePaymentTransaction.tenant_id == tenant_id,
                   LicensePaymentTransaction.ref_id == ref).first()
    if prior:
        details = json.loads(prior.payload_json or "{}")
        if details.get("request_id") != request_id:
            raise HTTPException(409, "Objednávku nelze vytvořit. Kontaktujte podporu.")
        if details.get("checkout_response"):
            return details["checkout_response"]
        raise HTTPException(409, "Objednávka již byla odeslána. Stav ověřte v historii plateb.")
    rows = db.query(LicensePaymentTransaction).filter(
        LicensePaymentTransaction.tenant_id == tenant_id,
        LicensePaymentTransaction.provider_status.in_(["CREATING", "PENDING", "PENDING_FALLBACK", "AUTHORIZED"])
    ).order_by(LicensePaymentTransaction.id.desc()).all()
    for row in rows:
        details = json.loads(row.payload_json or "{}")
        if details.get("request_id") == request_id:
            if details.get("checkout_response"):
                if row.plan != payload.plan or row.billing_period != payload.billing_period:
                    raise HTTPException(409, "Objednávka již existuje pro jiný tarif.")
                return details["checkout_response"]
            raise HTTPException(409, "Objednávka už byla odeslána. Stav ověřte v historii plateb; neopakujte platbu.")
        if row.provider_status in {"CREATING", "PENDING", "PENDING_FALLBACK", "AUTHORIZED"}:
            raise HTTPException(409, "Máte rozpracovanou platbu. Dokončete ji nebo ověřte její stav v historii plateb.")
    quote = _quote(payload, current_user, db)
    if (payload.billing_period != quote["billing_period"]
        or payload.expected_amount_halers != quote["amount_halers"]
        or payload.expected_currency != quote["currency"]
        or payload.expected_test_mode != quote["test_mode"]
        or payload.expected_recurring != quote["recurring"]):
        raise HTTPException(409, "Cena nebo režim platby se změnily. Načtěte objednávku znovu.")
    if quote["recurring"] and not payload.accept_recurring:
        raise HTTPException(400, "Potvrďte souhlas s pravidelným prodlužováním.")
    if not billing._load_comgate_config()["configured"]:
        raise HTTPException(503, "Online platby zatím nejsou dostupné.")
    # UUID is recorded in full; the gateway reference stays within its length limit.
    reservation = billing._record_payment_transaction(db, tenant_id=tenant_id, provider="comgate",
        trans_id=None, ref_id=ref, plan=payload.plan, billing_period=quote["billing_period"],
        amount_halers=quote["amount_halers"], currency=quote["currency"],
        event_type="checkout_started", provider_status="CREATING",
        payload=dict(request_id=request_id, checkout_test_mode=quote["test_mode"], legal_consents=dict(
            version=CONTRACT_VERSION, terms=True, immediate_service=True, recurring=quote["recurring"],
            customer_id=current_user.id, accepted_at=billing._utcnow().isoformat())))
    db.commit()
    try:
        result = billing.create_comgate_checkout(billing.ComgateCheckoutRequest(
            plan=payload.plan, billing_period=payload.billing_period, checkout_ref=ref,
            expected_amount=payload.expected_amount_halers, expected_currency=payload.expected_currency,
            expected_test_mode=payload.expected_test_mode, expected_recurring=payload.expected_recurring), request, current_user, db)
    except HTTPException as exc:
        # Unknown network outcomes stay reserved: never create a second charge blindly.
        if exc.status_code in {400, 409} or (exc.headers or {}).get("X-Comgate-Not-Created") == "1":
            reservation.provider_status = "CANCELLED"
            db.commit()
        raise
    db.refresh(reservation)
    details = json.loads(reservation.payload_json or "{}")
    response = result.model_dump()
    response["transaction_id"] = reservation.id
    details["checkout_response"] = response
    reservation.payload_json = json.dumps(details, ensure_ascii=False)
    if not result.requires_payment:
        reservation.provider_status = "APPLIED"
        reservation.event_type = "credit_applied"
    db.commit()
    return response


def _transaction(row):
    details = json.loads(row.payload_json or "{}")
    return dict(id=row.id, trans_id=row.trans_id, plan=row.plan, billing_period=row.billing_period,
                amount_halers=row.amount_halers, currency=row.currency, status=row.provider_status,
                confirmed=row.event_type in {"paid_confirmed", "renewal_paid", "test_paid_confirmed", "credit_applied"},
                test_mode=details.get("checkout_test_mode"), created_at=row.created_at,
                redirect_url=details.get("checkout_response", {}).get("redirect_url") if row.provider_status in {"PENDING", "PENDING_FALLBACK"} else None)


@router.get("/transactions")
def transactions(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(LicensePaymentTransaction).filter(LicensePaymentTransaction.tenant_id == _tenant(current_user)) \
             .order_by(LicensePaymentTransaction.id.desc()).limit(30).all()
    return dict(items=[_transaction(row) for row in rows])


@router.post("/transactions/{transaction_id}/refresh")
async def refresh(transaction_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(LicensePaymentTransaction).filter(LicensePaymentTransaction.id == transaction_id,
          LicensePaymentTransaction.tenant_id == _tenant(current_user)).first()
    if not row:
        raise HTTPException(404, "Platba nebyla nalezena.")
    if row.trans_id and not billing._is_trans_already_paid(db, row.trans_id):
        # Callback re-verifies with Comgate; return-link parameters never grant a license.
        from urllib.parse import urlencode
        synthetic = InternalRequest({"type":"http", "method":"GET", "headers":[],
                                     "query_string":urlencode({"transId":row.trans_id}).encode()})
        response = await billing.comgate_result(synthetic, db)
        if response.status_code >= 400:
            raise HTTPException(503, "Stav platby se nepodařilo ověřit. Zkuste to později.")
        db.refresh(row)
    return _transaction(row)


@router.get("/readiness")
def readiness(request: Request, current_user: Customer = Depends(get_current_user)):
    if current_user.role not in {"admin", "developer_admin"}:
        raise HTTPException(403, "Pouze pro administrátora.")
    cfg = billing._load_comgate_config()
    base = billing._request_backend_public_url(request)
    return dict(enabled=cfg["enabled"], configured=cfg["configured"], test_mode=cfg["test_mode"],
        merchant_present=bool(cfg["merchant"]), secret_present=bool(cfg["secret"]),
        callback_url=f"{base}/api/v1/license/comgate/result", return_url=f"{base}/web/payment-return.html",
        note="Adresu pro potvrzení plateb je nutné nastavit také v klientském portálu Comgate. Nastavení v aplikaci samo nepotvrzuje schválení obchodu.")


@router.post("/connection-check")
def connection_check(current_user: Customer = Depends(get_current_user)):
    """Read-only gateway check: does not create, cancel or charge a payment."""
    if current_user.role not in {"admin", "developer_admin"}:
        raise HTTPException(403, "Pouze pro administrátora.")
    cfg = billing._load_comgate_config()
    if not cfg['configured']:
        raise HTTPException(409, "Doplňte identifikátor propojení, tajný klíč a zapněte bránu v nastavení.")
    try:
        response = billing.httpx.post('https://payments.comgate.cz/v1.0/methods',
            data={'merchant':cfg['merchant'], 'secret':cfg['secret'], 'type':'json'}, timeout=15)
        data = response.json()
        methods = data.get('methods', [])
        if response.status_code != 200 or not isinstance(methods, list) or not methods:
            raise ValueError('gateway unavailable')
    except (ValueError, billing.httpx.HTTPError):
        raise HTTPException(503, "Spojení nebylo potvrzeno. Zkontrolujte údaje propojení a povolené IP adresy v Comgate.")
    return dict(ok=True, message="Spojení s Comgate funguje. Tento test nic neúčtuje; potvrzení plateb a opakování se ověřují samostatně.",
                method_count=len(methods), checked_at=billing._utcnow().isoformat())
