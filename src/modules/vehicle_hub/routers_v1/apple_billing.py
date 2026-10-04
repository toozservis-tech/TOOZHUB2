"""Authenticated Apple purchase sync + signed App Store Server Notifications V2."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from appstoreserverlibrary.signed_data_verifier import VerificationException

from src.modules.licensing import apple_store as store
from src.modules.licensing.apple_models import AppleBillingIdentity, AppleSubscription
from ..database import get_db
from ..models import Customer, License, LicenseSubscription
from .auth import get_current_user

router = APIRouter(prefix="/apple", tags=["App Store"])


class SignedTransaction(BaseModel):
    signed_transaction: str = Field(min_length=10, max_length=50000)


class Notification(BaseModel):
    signedPayload: str = Field(min_length=10, max_length=100000)


def _status(db, user):
    from src.modules.licensing.service import get_or_create_license
    license = get_or_create_license(db, user.tenant_id) if user.tenant_id else None
    sub = db.query(LicenseSubscription).filter_by(tenant_id=user.tenant_id).first()
    return dict(plan=license.plan if license else "free", provider=sub.provider if sub else None,
                status=sub.status if sub else None, expires_at=sub.current_period_end if sub else None,
                auto_renew=sub.auto_renew_enabled if sub else False)


@router.get("/catalog")
def catalog(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        cfg = store.config()
        store.require_schema(db)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        return dict(enabled=False, message=exc.detail, products=[], **_status(db, current_user))
    from .mobile_billing import FEATURES
    return dict(enabled=True, message=None, environment=cfg.environment.value,
        products=[dict(id=key, plan=plan, period=period, vehicles_limit=store.PLAN_LIMITS[plan],
                  features=[title for flag, title in FEATURES.items() if store.PLAN_FEATURES[plan].get(flag)])
                  for key, (plan, period) in store.PRODUCTS.items()], **_status(db, current_user))


@router.post("/session")
def purchase_session(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = store.config()
    store.require_schema(db)
    identity = store.identity_for_user(db, current_user)
    store.assert_account_owner(db, identity)
    blocked = store.other_paid_license(db, current_user.tenant_id)
    db.commit()
    return dict(app_account_token=identity.token, can_purchase=not blocked,
                message="Účet má již placený tarif. Před další objednávkou kontaktujte podporu." if blocked else None,
                environment=cfg.environment.value, bundle_id=cfg.bundle_id)


@router.post("/sync")
def sync_purchase(payload: SignedTransaction, request: Request,
                  current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    from src.server.routers.user_auth import _limit_auth
    _limit_auth(request, "apple-sync", current_user.email, calls=30)
    cfg = store.config()
    store.require_schema(db)
    verifier, _ = store.apple_services(cfg)
    try:
        tx = verifier.verify_and_decode_signed_transaction(payload.signed_transaction)
    except VerificationException:
        raise HTTPException(400, "Podpis nákupu se nepodařilo ověřit.") from None
    identity = store.identity_for_user(db, current_user)
    store.check_transaction(tx, cfg, identity.token)
    try:
        store.synchronize(db, identity, tx.originalTransactionId, cfg)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return dict(verified=True, **_status(db, current_user))


@router.post("/check-account")
def check_purchase_account(payload: SignedTransaction,
                           current_user: Customer = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """Check signed history before showing Apple's purchase/upgrade sheet.

    Apple's mutable appAccountToken cannot overwrite our original account
    binding. This read-only check neither grants a licence nor transfers it.
    """
    cfg = store.config()
    store.require_schema(db)
    verifier, _ = store.apple_services(cfg)
    try:
        tx = verifier.verify_and_decode_signed_transaction(payload.signed_transaction)
    except VerificationException:
        raise HTTPException(400, "Historii nákupu se nepodařilo ověřit.") from None
    signed_token = store.check_transaction(tx, cfg)
    identity = db.query(AppleBillingIdentity).filter_by(customer_id=current_user.id).first()
    if identity is None:
        raise HTTPException(409, "Načtěte tarify znovu a zopakujte nákup.")
    if identity.tenant_id != current_user.tenant_id:
        raise HTTPException(409, "Předplatné patří k původnímu účtu. Kontaktujte podporu.")
    store.assert_account_owner(db, identity)
    previous = db.get(AppleSubscription, f"{cfg.environment.value}:{tx.originalTransactionId}")
    # A known original transaction remains with its first verified owner, even
    # if a later upgrade supplied a different appAccountToken to Apple.
    owner_token = previous.account_token if previous else signed_token
    allowed = owner_token == identity.token
    return dict(can_purchase=allowed, message=None if allowed else (
        "Tento účet Apple již používá předplatné jiného účtu SprávaVozidel. "
        "Přihlaste se k původnímu účtu SprávaVozidel, nebo použijte jiný účet Apple. "
        "Žádný nový nákup nebyl zahájen."
    ))


@router.post("/notifications")
def notifications(payload: Notification, db: Session = Depends(get_db)):
    cfg = store.config()
    store.require_schema(db)
    verifier, _ = store.apple_services(cfg)
    try:
        notification = verifier.verify_and_decode_notification(payload.signedPayload)
        if notification.notificationType == "TEST":
            return {"received": True}
        data = notification.data
        if not data or not data.signedTransactionInfo:
            return {"received": True}
        tx = verifier.verify_and_decode_signed_transaction(data.signedTransactionInfo)
    except VerificationException:
        raise HTTPException(400, "Neplatný podpis oznámení.") from None
    token = store.check_transaction(tx, cfg)
    identity = db.get(AppleBillingIdentity, token)
    if identity is None or identity.customer_id is None or identity.tenant_id is None:
        # Deleted account: do not resurrect data or transfer access to another user.
        return {"received": True}
    try:
        # Always re-read Apple's current state, including duplicates/out-of-order notifications.
        store.synchronize(db, identity, tx.originalTransactionId, cfg)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"received": True}
