"""StoreKit 2 verification. Device claims never directly grant a paid license.

Each sync reads current status from Apple's authenticated API, then verifies every
signed transaction and renewal record with Apple's library and pinned root CAs.
The integration is closed until server credentials, schema and products are ready.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import inspect
from appstoreserverlibrary.api_client import AppStoreServerAPIClient
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from .apple_models import AppleBillingIdentity, AppleSubscription, AppleReconciliationState
from .service import PLAN_FEATURES, PLAN_LIMITS
from src.modules.vehicle_hub.models import Customer, License, LicenseSubscription, LicensePaymentTransaction, Tenant

PRODUCTS = {
    f"cz.toozservis.spravavozidel.{plan}.{period}": (plan, period)
    for plan in ("basic", "premium") for period in ("monthly", "yearly")
}


@dataclass(frozen=True)
class AppleConfig:
    bundle_id: str
    app_id: int
    group_id: str
    environment: Environment
    key_id: str
    issuer_id: str
    private_key: str


def config():
    if os.getenv("APPLE_IAP_ENABLED") != "1":
        raise HTTPException(503, "Předplatné přes App Store ještě není dostupné.")
    try:
        cfg = AppleConfig(
            bundle_id=os.environ["APPLE_IAP_BUNDLE_ID"], app_id=int(os.environ["APPLE_IAP_APP_ID"]),
            group_id=os.environ["APPLE_IAP_SUBSCRIPTION_GROUP_ID"],
            environment=Environment(os.getenv("APPLE_IAP_ENVIRONMENT", "Production")),
            key_id=os.environ["APPLE_IAP_KEY_ID"], issuer_id=os.environ["APPLE_IAP_ISSUER_ID"],
            private_key=os.environ["APPLE_IAP_PRIVATE_KEY"].replace("\\n", "\n"))
        if cfg.environment not in (Environment.PRODUCTION, Environment.SANDBOX) or not all(
            [cfg.bundle_id, cfg.app_id > 0, cfg.group_id, cfg.key_id, cfg.issuer_id, cfg.private_key]
        ):
            raise ValueError()
        return cfg
    except (KeyError, ValueError):
        raise HTTPException(503, "Propojení App Storu ještě není dokončené.") from None


@lru_cache(maxsize=2)
def apple_services(cfg):
    roots = [p.read_bytes() for p in sorted((Path(__file__).parent / "apple_roots").glob("*.cer"))]
    if not roots:
        raise HTTPException(503, "Ověření App Storu není dostupné.")
    verifier = SignedDataVerifier(roots, True, cfg.environment, cfg.bundle_id, cfg.app_id)
    client = AppStoreServerAPIClient(cfg.private_key, cfg.key_id, cfg.issuer_id, cfg.bundle_id, cfg.environment)
    return verifier, client


def require_schema(db):
    existing = set(inspect(db.get_bind()).get_table_names())
    if not {AppleBillingIdentity.__tablename__, AppleSubscription.__tablename__, AppleReconciliationState.__tablename__} <= existing:
        raise HTTPException(503, "Databáze předplatného čeká na dokončení nastavení.")


def identity_for_user(db, user):
    if not user.tenant_id:
        raise HTTPException(403, "Účet nemá přiřazenou organizaci.")
    # Serializes token creation and billing changes for the tenant in PostgreSQL.
    db.query(Tenant).filter(Tenant.id == user.tenant_id).with_for_update().one()
    identity = db.query(AppleBillingIdentity).filter_by(customer_id=user.id).first()
    if identity is None:
        identity = AppleBillingIdentity(token=str(uuid4()), customer_id=user.id, tenant_id=user.tenant_id)
        db.add(identity)
        db.flush()
    if identity.tenant_id != user.tenant_id:
        raise HTTPException(409, "Předplatné patří k původnímu účtu. Kontaktujte podporu.")
    return identity


def other_paid_license(db, tenant_id):
    sub = db.query(LicenseSubscription).filter_by(tenant_id=tenant_id).first()
    license = db.query(License).filter_by(tenant_id=tenant_id).first()
    pending = db.query(LicensePaymentTransaction.id).filter(
        LicensePaymentTransaction.tenant_id == tenant_id,
        LicensePaymentTransaction.provider == "comgate",
        LicensePaymentTransaction.provider_status.in_(["CREATING", "PENDING", "PENDING_FALLBACK", "AUTHORIZED"]),
    ).first()
    if pending:
        return True
    if sub and sub.provider == "apple":
        return False
    # Do not sell a second subscription over an existing paid/manual entitlement.
    return bool(license and license.plan != "free" and license.status == "active"
                and (not license.valid_to or license.valid_to > datetime.utcnow())) or bool(
                    sub and sub.auto_renew_enabled)


def assert_account_owner(db, identity):
    other = db.query(AppleSubscription).join(AppleBillingIdentity).filter(
        AppleBillingIdentity.tenant_id == identity.tenant_id,
        AppleSubscription.account_token != identity.token,
        AppleSubscription.active.is_(True),
        AppleSubscription.access_until > datetime.utcnow(),
    ).first()
    if other:
        raise HTTPException(409, "Organizace již má předplatné propojené s jiným účtem SprávaVozidel.")


def timestamp(value):
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HTTPException(400, "Potvrzení App Storu neobsahuje platné datum.")
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        raise HTTPException(400, "Datum potvrzení App Storu není platné.") from None


def check_transaction(tx, cfg, account_token=None):
    if (tx.bundleId != cfg.bundle_id or tx.environment != cfg.environment
        or tx.productId not in PRODUCTS or tx.subscriptionGroupIdentifier != cfg.group_id
        or tx.type != "Auto-Renewable Subscription" or tx.inAppOwnershipType != "PURCHASED"
        or not tx.originalTransactionId or not tx.transactionId):
        raise HTTPException(400, "Nákup nepatří k tomuto předplatnému SprávaVozidel.")
    try:
        token = str(UUID(tx.appAccountToken or ""))
    except ValueError:
        raise HTTPException(403, "Nákup není propojený s účtem SprávaVozidel.") from None
    if account_token and token != account_token:
        raise HTTPException(403, "Nákup patří jinému účtu SprávaVozidel.")
    return token


def synchronize(db, identity, original_id, cfg):
    verifier, client = apple_services(cfg)
    try:
        response = client.get_all_subscription_statuses(original_id)
        if (response.bundleId != cfg.bundle_id or response.environment != cfg.environment
            or (cfg.environment == Environment.PRODUCTION and response.appAppleId != cfg.app_id)):
            raise HTTPException(400, "App Store vrátil předplatné jiné aplikace.")
        snapshots = []
        for group in response.data or []:
            if group.subscriptionGroupIdentifier != cfg.group_id:
                continue
            for item in group.lastTransactions or []:
                tx = verifier.verify_and_decode_signed_transaction(item.signedTransactionInfo)
                check_transaction(tx, cfg, identity.token)
                renewal = verifier.verify_and_decode_renewal_info(item.signedRenewalInfo)
                if (item.originalTransactionId != tx.originalTransactionId
                    or renewal.originalTransactionId != tx.originalTransactionId
                    or renewal.environment != cfg.environment
                    or (renewal.appAccountToken and str(UUID(renewal.appAccountToken)) != identity.token)):
                    raise HTTPException(400, "Údaje obnovování předplatného nesouhlasí.")
                expiry = timestamp(tx.expiresDate)
                until = expiry
                if item.status == 4 and renewal.gracePeriodExpiresDate:
                    until = max(expiry, timestamp(renewal.gracePeriodExpiresDate))
                signed = max(tx.signedDate or 0, renewal.signedDate or 0)
                timestamp(signed)
                if signed > int(datetime.now(timezone.utc).timestamp() * 1000) + 300_000:
                    raise HTTPException(400, "Čas potvrzení App Storu nesouhlasí.")
                active = bool(item.status in (1, 4) and until > datetime.utcnow()
                              and not tx.revocationDate and not tx.isUpgraded)
                snapshots.append(dict(
                    id=f"{cfg.environment.value}:{tx.originalTransactionId}", account_token=identity.token,
                    environment=cfg.environment.value, original_transaction_id=tx.originalTransactionId,
                    transaction_id=tx.transactionId, product_id=tx.productId,
                    plan=PRODUCTS[tx.productId][0], period=PRODUCTS[tx.productId][1],
                    status=int(item.status), signed_date=signed, expires_at=expiry, access_until=until,
                    auto_renew=renewal.autoRenewStatus == 1, active=active))
        if not snapshots or original_id not in {s["original_transaction_id"] for s in snapshots}:
            raise HTTPException(409, "App Store zatím nepotvrdil stav předplatného. Zkuste obnovení nákupů později.")
    except HTTPException:
        raise
    except VerificationException:
        raise HTTPException(400, "Podpis nákupu se nepodařilo ověřit.") from None
    except Exception:
        # Do not leak private keys, JWS payloads or upstream response internals.
        raise HTTPException(503, "App Store nyní nelze ověřit. Nákup zůstává uložený u Applu; zkuste to později.") from None

    tenant_id = identity.tenant_id
    tenant = db.query(Tenant).filter_by(id=tenant_id).with_for_update().first()
    db.refresh(identity)
    owner = db.query(Customer).filter_by(id=identity.customer_id).populate_existing().with_for_update().first() if identity.customer_id else None
    if not tenant or not owner or owner.is_deleted or identity.tenant_id != tenant_id or owner.tenant_id != tenant_id:
        raise HTTPException(409, "Účet předplatného již není dostupný.")
    assert_account_owner(db, identity)
    for snapshot in snapshots:
        row = db.get(AppleSubscription, snapshot["id"])
        if row and row.account_token != identity.token:
            raise HTTPException(403, "Předplatné je již propojené s jiným účtem.")
        if row and (row.signed_date > snapshot["signed_date"] or
                    (row.signed_date == snapshot["signed_date"] and row.status == 5 and snapshot["active"])):
            continue  # An older concurrent reply cannot resurrect a revoked entitlement.
        if row is None:
            row = AppleSubscription(**snapshot)
            db.add(row)
        else:
            for key, value in snapshot.items():
                setattr(row, key, value)
    db.flush()
    apply_entitlement(db, identity, cfg)


def apply_entitlement(db, identity, cfg):
    assert_account_owner(db, identity)
    if other_paid_license(db, identity.tenant_id):
        raise HTTPException(409, "Účet má jiné placené předplatné. Kontaktujte podporu, aby nevznikla dvojí platba.")
    active = db.query(AppleSubscription).filter_by(account_token=identity.token,
        environment=cfg.environment.value, active=True).filter(AppleSubscription.access_until > datetime.utcnow()).all()
    best = max(active, key=lambda s: (s.plan == "premium", s.access_until), default=None)
    sub = db.query(LicenseSubscription).filter_by(tenant_id=identity.tenant_id).first()
    if not best and (not sub or sub.provider != "apple"):
        return
    if sub is None:
        sub = LicenseSubscription(tenant_id=identity.tenant_id, provider="apple")
        db.add(sub)
    sub.provider = "apple"
    sub.plan_current = best.plan if best else "free"
    sub.status = ("grace" if best.status == 4 else "active") if best else "canceled"
    sub.auto_renew_enabled = best.auto_renew if best else False
    sub.billing_period = best.period if best else sub.billing_period
    sub.current_period_end = best.access_until if best else sub.current_period_end
    sub.last_trans_id = best.transaction_id if best else sub.last_trans_id
    sub.init_recurring_id = None
    sub.next_charge_at = None  # Only Apple is allowed to charge Apple subscriptions.
    sub.pending_plan_change = None
    license = db.query(License).filter_by(tenant_id=identity.tenant_id).first()
    if license is None:
        license = License(tenant_id=identity.tenant_id)
        db.add(license)
    license.plan = sub.plan_current
    license.status = "active"
    license.valid_to = best.access_until if best else None
    license.vehicles_limit = PLAN_LIMITS[license.plan]
    for flag in ("vin_decode_enabled", "ares_enabled", "reminders_enabled"):
        setattr(license, flag, PLAN_FEATURES[license.plan][flag])
    db.flush()
