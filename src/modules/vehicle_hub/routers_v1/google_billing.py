"""Authenticated Google Play purchase verification + authenticated Pub/Sub RTDN."""
import base64
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session
from src.modules.licensing import google_store as store
from src.modules.licensing.google_models import GoogleBillingIdentity, GoogleSubscription
from src.modules.licensing.service import get_or_create_license
from ..database import get_db
from ..models import Customer, LicenseSubscription
from .auth import get_current_user

router = APIRouter(prefix="/google", tags=["Google Play"])


class Purchase(BaseModel):
    purchase_token: SecretStr


class Restore(BaseModel):
    purchase_tokens: list[SecretStr] = Field(default_factory=list, max_length=20)


def status(db, user):
    lic = get_or_create_license(db, user.tenant_id, commit_changes=False) if user.tenant_id else None
    sub = db.query(LicenseSubscription).filter_by(tenant_id=user.tenant_id).first()
    return dict(plan=lic.plan if lic else "free", provider=sub.provider if sub else None,
                status=sub.status if sub else None, expires_at=sub.current_period_end if sub else None,
                billing_period=sub.billing_period if sub else None, auto_renew=bool(sub and sub.auto_renew_enabled))


def limit(request, user, kind="sync", calls=30):
    from src.server.routers.user_auth import _limit_auth
    _limit_auth(request, "google-" + kind, user.email, calls=calls, period=60)


@router.get("/catalog")
def catalog(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        cfg = store.config()
        store.require_schema(db)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        result = dict(enabled=False, message=exc.detail, package_name=store.PACKAGE_NAME, products=[], **status(db, current_user))
        db.commit()
        return result
    from .mobile_billing import FEATURES
    result = dict(enabled=True, message=None, package_name=cfg.package_name,
        products=[dict(product_id=product, base_plan_id=base_plan, plan=plan, period=period,
                       vehicles_limit=store.PLAN_LIMITS[plan],
                       features=[title for flag, title in FEATURES.items() if store.PLAN_FEATURES[plan].get(flag)])
                  for (product, base_plan), (plan, period) in store.PRODUCTS.items()], **status(db, current_user))
    db.commit()
    return result


@router.post("/session")
def purchase_session(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        cfg = store.config()
        store.require_schema(db)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        result = dict(can_purchase=False, reason="not_configured", message=exc.detail,
            obfuscated_account_id=None, package_name=store.PACKAGE_NAME, **status(db, current_user))
        db.commit()
        return result
    if not store.eligible(current_user):
        return dict(can_purchase=False, reason="account_ineligible", obfuscated_account_id=None,
            message="Nákup je dostupný v zákaznickém účtu.", package_name=cfg.package_name, **status(db, current_user))
    identity = store.identity_for_user(db, current_user)
    store.assert_account_owner(db, identity)
    blocked = store.other_paid_license(db, current_user.tenant_id)
    result = dict(can_purchase=not blocked, reason="other_provider" if blocked else None,
        message="Účet již má placený tarif nebo rozpracovanou platbu. Spravujte stávající předplatné." if blocked else None,
        obfuscated_account_id=identity.token, package_name=cfg.package_name, **status(db, current_user))
    db.commit()
    return result


def sync_one(db, user, token, cfg):
    try:
        identity = store.identity_for_user(db, user)
        row = store.synchronize(db, identity, token, cfg)
        subscription_id = row.id
        db.commit()  # Durable entitlement BEFORE acknowledgement of the purchase.
    except Exception:
        db.rollback()
        raise
    return store.acknowledge_committed(db, subscription_id, cfg)


@router.post("/sync")
def sync_purchase(payload: Purchase, request: Request,
                  current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    limit(request, current_user)
    cfg = store.config(); store.require_schema(db)
    pending = sync_one(db, current_user, payload.purchase_token.get_secret_value(), cfg)
    result = dict(verified=True, acknowledgement_pending=pending, **status(db, current_user))
    db.commit()
    return result


@router.post("/restore")
def restore(payload: Restore, request: Request,
            current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    limit(request, current_user, "restore", 6)
    cfg = store.config(); store.require_schema(db)
    restored, rejected, pending = 0, 0, False
    # Deduplicate without leaking raw tokens in any response or logging.
    tokens = dict.fromkeys(item.get_secret_value() for item in payload.purchase_tokens)
    for token in tokens:
        try:
            pending = sync_one(db, current_user, token, cfg) or pending
            restored += 1
        except HTTPException as exc:
            db.rollback()
            if exc.status_code >= 500:
                raise  # A temporary outage must not look like a completed restore.
            rejected += 1
    result = dict(verified=True, restored_count=restored, rejected_count=rejected,
                  acknowledgement_pending=pending, **status(db, current_user))
    db.commit()
    return result


@router.post("/reconcile")
def reconcile(request: Request, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    limit(request, current_user, "reconcile", 12)
    cfg = store.config(); store.require_schema(db)
    identity = db.query(GoogleBillingIdentity).filter_by(customer_id=current_user.id).first()
    checked = 0
    if identity:
        from datetime import datetime, timedelta
        # A profile refresh is bounded. The worker maintains the rest of the queue.
        rows = db.query(GoogleSubscription).filter_by(account_token=identity.token, superseded_by=None).filter(
            GoogleSubscription.verified_at < datetime.utcnow() - timedelta(seconds=60)).order_by(
            GoogleSubscription.verified_at).limit(3).all()
        tokens = [store.decrypt_token(row, cfg) for row in rows]
        for token in tokens:
            sync_one(db, current_user, token, cfg)
            checked += 1
    result = dict(verified=True, checked=checked, **status(db, current_user))
    db.commit()
    return result


def verify_push(request, cfg):
    authorization = request.headers.get("authorization", "")
    if not cfg.push_audience or not cfg.push_service_account or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Neplatné ověření oznámení Google Play.")
    try:
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request as GoogleRequest
        # Limit Google's certificate fetch too; invalid auth cannot hang workers.
        class BoundedRequest(GoogleRequest):
            def __call__(self, *args, **kwargs):
                kwargs["timeout"] = 10
                return super().__call__(*args, **kwargs)
        claims = id_token.verify_oauth2_token(authorization[7:], BoundedRequest(), audience=cfg.push_audience)
        if (claims.get("email") != cfg.push_service_account or claims.get("email_verified") is not True
                or claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com")):
            raise ValueError()
    except Exception:
        raise HTTPException(401, "Neplatné ověření oznámení Google Play.") from None


@router.post("/notifications")
def notifications(payload: dict, request: Request, db: Session = Depends(get_db)):
    cfg = store.config(); store.require_schema(db)
    verify_push(request, cfg)
    try:
        body = json.dumps(payload).encode()
        if len(body) > 100_000:
            raise ValueError()
        envelope = payload
        data = json.loads(base64.b64decode(envelope["message"]["data"], validate=True))
        if data.get("packageName") != cfg.package_name:
            raise ValueError()
        if "testNotification" in data:
            return {"received": True}
        # Both subscription and voided purchase RTDN are mere hints: fetch current API state.
        hint = data.get("subscriptionNotification") or data.get("voidedPurchaseNotification") or {}
        token = store.validate_token(hint.get("purchaseToken"))
    except (ValueError, TypeError, KeyError, HTTPException):
        raise HTTPException(400, "Neplatné oznámení Google Play.") from None
    row = db.get(GoogleSubscription, store.fingerprint(token, cfg))
    if row:
        identity = db.get(GoogleBillingIdentity, row.account_token)
    else:
        verified = store.publisher(cfg).get(token)
        account = (verified.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId")
        if not account:
            account = ((verified.get("outOfAppPurchaseContext") or {}).get("expiredExternalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId")
        identity = db.get(GoogleBillingIdentity, account) if isinstance(account, str) else None
    user = db.get(Customer, identity.customer_id) if identity and identity.customer_id else None
    if not user or not identity.tenant_id or not store.eligible(user):
        return {"received": True}  # Deleted/unknown account cannot be resurrected or transferred.
    # Re-fetch under the tenant lock; do not trust event ordering or supplied status.
    sync_one(db, user, token, cfg)
    return {"received": True}
