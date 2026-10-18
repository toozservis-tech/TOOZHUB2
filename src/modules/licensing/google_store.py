"""Google Play purchases: authoritative API verification, never client-only grants.

Remote reads and entitlement writes are serialized per tenant. Linked purchase
tokens are irreversibly superseded; an old token cannot restore replaced access.
Acknowledgement happens only AFTER the verified entitlement has been committed.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import inspect, or_

from .google_models import GoogleBillingIdentity, GoogleSubscription
from .service import PLAN_FEATURES, PLAN_LIMITS
from src.modules.vehicle_hub.models import Customer, License, LicenseSubscription, LicensePaymentTransaction, Tenant

PACKAGE_NAME = "cz.toozservis.spravavozidel.android"
PRODUCTS = {(f"evidence_vozidel_{plan}", period): (plan, period)
            for plan in ("basic", "premium") for period in ("monthly", "yearly")}
STATES = {"SUBSCRIPTION_STATE_PENDING", "SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_PAUSED",
          "SUBSCRIPTION_STATE_IN_GRACE_PERIOD", "SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_CANCELED",
          "SUBSCRIPTION_STATE_EXPIRED", "SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED"}
ACCESS_STATES = {"SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD", "SUBSCRIPTION_STATE_CANCELED"}


class _TokenURLFilter(logging.Filter):
    def filter(self, record):
        # urllib3 debug logging normally includes the full request URL. Google
        # puts purchase tokens in URL paths, so redact even if DEBUG is enabled.
        message = record.getMessage()
        if "/tokens/" in message:
            record.msg = re.sub(r"(/tokens/)[^\s\"'?#]+", r"\1[redacted]", message)
            record.args = ()
        return True


for _logger in ("urllib3.connectionpool", "google.auth.transport.requests"):
    logging.getLogger(_logger).addFilter(_TokenURLFilter())


@dataclass(frozen=True)
class GoogleConfig:
    package_name: str
    service_account_json: str = field(repr=False)
    token_key: str = field(repr=False)
    allow_test_purchases: bool = False
    push_audience: str = ""
    push_service_account: str = ""
    test_customer_ids: frozenset[int] = frozenset()


def config():
    if os.getenv("GOOGLE_PLAY_ENABLED") != "1":
        raise HTTPException(503, "Předplatné přes Google Play ještě není dostupné.")
    try:
        cfg = GoogleConfig(os.environ["GOOGLE_PLAY_PACKAGE_NAME"], os.environ["GOOGLE_PLAY_SERVICE_ACCOUNT_JSON"],
            os.environ["GOOGLE_PLAY_TOKEN_KEY"], os.getenv("GOOGLE_PLAY_ALLOW_TEST_PURCHASES") == "1",
            os.getenv("GOOGLE_PLAY_PUSH_AUDIENCE", ""), os.getenv("GOOGLE_PLAY_PUSH_SERVICE_ACCOUNT", ""),
            frozenset(int(item) for item in os.getenv("GOOGLE_PLAY_TEST_CUSTOMER_IDS", "").split(",") if item.strip()))
        info = json.loads(cfg.service_account_json)
        if (cfg.package_name != PACKAGE_NAME or info.get("type") != "service_account"
            or info.get("token_uri") != "https://oauth2.googleapis.com/token"
            or not info.get("private_key") or not info.get("client_email")):
            raise ValueError()
        Fernet(cfg.token_key.encode("ascii"))
        # Missing official runtime dependency must fail closed before a purchase sheet opens.
        from google.oauth2 import service_account
        service_account.Credentials.from_service_account_info(info,
            scopes=["https://www.googleapis.com/auth/androidpublisher"])
        return cfg
    except (KeyError, ValueError, TypeError, UnicodeError, ImportError):
        raise HTTPException(503, "Propojení Google Play ještě není dokončené.") from None


class Publisher:
    def __init__(self, cfg):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        credentials = service_account.Credentials.from_service_account_info(json.loads(cfg.service_account_json),
            scopes=["https://www.googleapis.com/auth/androidpublisher"])
        self.session = AuthorizedSession(credentials, refresh_timeout=10)
        self.prefix = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/" + quote(cfg.package_name, safe="")

    def request(self, method, path, payload=None):
        try:
            response = self.session.request(method, self.prefix + path, json=payload, timeout=(5, 20),
                                            allow_redirects=False, max_allowed_time=30)
            if response.status_code in (404, 410):
                raise HTTPException(400, "Google Play tento nákup nepotvrdil. Obnovte nákupy a zkuste to znovu.")
            if response.status_code != 200 or len(response.content) > 200_000:
                raise HTTPException(503, "Ověření u Google Play je dočasně nedostupné.")
            return response.json() if response.content else {}
        except HTTPException:
            raise
        except Exception:
            # URLs and upstream errors contain purchase tokens / OAuth credentials.
            raise HTTPException(503, "Ověření u Google Play je dočasně nedostupné.") from None

    def get(self, token):
        return self.request("GET", "/purchases/subscriptionsv2/tokens/" + quote(token, safe=""))

    def acknowledge(self, product, token, account_token):
        return self.request("POST", "/purchases/subscriptions/" + quote(product, safe="") + "/tokens/" +
            quote(token, safe="") + ":acknowledge", {"externalAccountIds": {"obfuscatedAccountId": account_token}})


def publisher(cfg):
    # Per operation session: AuthorizedSession credentials are not shared across threads.
    return Publisher(cfg)


def require_schema(db):
    if not {"google_billing_identities", "google_subscriptions"} <= set(inspect(db.connection()).get_table_names()):
        raise HTTPException(503, "Databáze Google Play čeká na dokončení nastavení.")


def eligible(user):
    return bool(user.tenant_id and user.role == "user" and not user.is_deleted and not getattr(user, "is_disabled", False))


def identity_for_user(db, user):
    if not eligible(user):
        raise HTTPException(403, "Nákup předplatného je dostupný v zákaznickém účtu.")
    db.query(Tenant).filter_by(id=user.tenant_id).with_for_update().one()
    identity = db.query(GoogleBillingIdentity).filter_by(customer_id=user.id).first()
    if identity is None:
        identity = GoogleBillingIdentity(token=secrets.token_hex(32), customer_id=user.id, tenant_id=user.tenant_id)
        db.add(identity); db.flush()
    if identity.tenant_id != user.tenant_id:
        raise HTTPException(409, "Předplatné patří k původnímu účtu. Kontaktujte podporu.")
    return identity


def other_paid_license(db, tenant_id):
    sub = db.query(LicenseSubscription).filter_by(tenant_id=tenant_id).populate_existing().first()
    lic = db.query(License).filter_by(tenant_id=tenant_id).populate_existing().first()
    if db.query(LicensePaymentTransaction.id).filter(LicensePaymentTransaction.tenant_id == tenant_id,
            LicensePaymentTransaction.provider == "comgate", LicensePaymentTransaction.provider_status.in_(
                ["CREATING", "PENDING", "PENDING_FALLBACK", "AUTHORIZED"])).first():
        return True
    if sub and sub.provider == "google":
        return False
    return bool(lic and lic.plan != "free" and lic.status == "active" and
                (not lic.valid_to or lic.valid_to > datetime.utcnow())) or bool(sub and sub.auto_renew_enabled)


def assert_account_owner(db, identity):
    if db.query(GoogleSubscription.id).join(GoogleBillingIdentity).filter(
        GoogleBillingIdentity.tenant_id == identity.tenant_id, GoogleSubscription.account_token != identity.token,
        GoogleSubscription.superseded_by.is_(None), or_(
            GoogleSubscription.active.is_(True) & (GoogleSubscription.expires_at > datetime.utcnow()),
            GoogleSubscription.state.in_(["SUBSCRIPTION_STATE_ACTIVE", "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
                "SUBSCRIPTION_STATE_PENDING", "SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"]))).first():
        raise HTTPException(409, "Organizace má předplatné propojené s jiným účtem Evidence Vozidel.")


def validate_token(token):
    if not isinstance(token, str) or not 10 <= len(token) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise HTTPException(400, "Neplatné potvrzení nákupu Google Play.")
    return token


def fingerprint(token, cfg):
    return hashlib.sha256((cfg.package_name + "\0" + validate_token(token)).encode()).hexdigest()


def encrypt_token(token, cfg, identity):
    payload = json.dumps([cfg.package_name, identity.token, token], separators=(",", ":")).encode()
    return Fernet(cfg.token_key.encode()).encrypt(payload).decode()


def decrypt_token(row, cfg):
    try:
        package, identity, token = json.loads(Fernet(cfg.token_key.encode()).decrypt(row.encrypted_token.encode()))
        if package != cfg.package_name or identity != row.account_token or fingerprint(token, cfg) != row.id:
            raise ValueError()
        return token
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        raise HTTPException(503, "Obnovení Google Play čeká na kontrolu nastavení serveru.") from None


def parse_time(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.year < 2000:
            raise ValueError()
        return result.astimezone(timezone.utc).replace(tzinfo=None)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise HTTPException(400, "Google Play vrátil neplatné datum předplatného.") from None


def snapshot(data, cfg):
    if not isinstance(data, dict) or data.get("kind") != "androidpublisher#subscriptionPurchaseV2":
        raise HTTPException(400, "Google Play nevrátil platné předplatné.")
    state = data.get("subscriptionState")
    if state not in STATES or data.get("acknowledgementState") not in {
            "ACKNOWLEDGEMENT_STATE_PENDING", "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"}:
        raise HTTPException(400, "Stav nákupu u Google Play není podporovaný.")
    is_test = "testPurchase" in data
    if is_test and not cfg.allow_test_purchases:
        raise HTTPException(403, "Testovací nákup není na tomto serveru povolený.")
    items = data.get("lineItems")
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise HTTPException(400, "Google Play nevrátil položky předplatného.")
    current, future = [], []
    for item in items:
        offer = item.get("offerDetails") or {}
        pair = (item.get("productId"), offer.get("basePlanId"))
        if pair not in PRODUCTS or offer.get("offerId") or "prepaidPlan" in item:
            raise HTTPException(400, "Nákup nepatří k podporovanému tarifu Evidence Vozidel.")
        # A deferred replacement is not owned yet: no successful order / expiry.
        expiry = parse_time(item["expiryTime"]) if item.get("expiryTime") else None
        entry = dict(product_id=pair[0], base_plan_id=pair[1], plan=PRODUCTS[pair][0], period=PRODUCTS[pair][1],
                     expires_at=expiry, auto_renew=bool((item.get("autoRenewingPlan") or {}).get("autoRenewEnabled")))
        (current if expiry and (len(items) == 1 or item.get("latestSuccessfulOrderId")) else future).append(entry)
    # After a deferred switch Google can return the expired old item alongside
    # the now-owned new item. Select the single currently unexpired owned item.
    unexpired = [entry for entry in current if entry["expires_at"] > datetime.utcnow()]
    if len(unexpired) > 1:
        # Multiple concurrent add-ons are not sold by this application. Fail closed.
        raise HTTPException(400, "Google Play vrátil více současných tarifů; kontaktujte podporu.")
    chosen = unexpired[0] if unexpired else max(current, key=lambda entry: entry["expires_at"]) if current else future[0]
    active = bool(unexpired and state in ACCESS_STATES)
    return dict(**chosen, state=state, active=active, test_purchase=is_test,
                acknowledged=data["acknowledgementState"] == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED")


def _owner_matches(data, identity, known=None):
    external = (data.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId")
    # Google may omit external identifiers on old acknowledged records; only an
    # already verified immutable binding may substitute, never a client account.
    if external is None and known and known.account_token == identity.token:
        return
    if not isinstance(external, str) or not hmac.compare_digest(external, identity.token):
        raise HTTPException(403, "Tento nákup patří jinému účtu Evidence Vozidel.")


def synchronize(db, identity, token, cfg):
    if not identity.tenant_id or not identity.customer_id:
        raise HTTPException(403, "Původní účet předplatného již není dostupný.")
    # Lock BEFORE fetching current Google state to prevent late stale responses
    # from overwriting a newer refund/revocation or another store's purchase.
    db.query(Tenant).filter_by(id=identity.tenant_id).with_for_update().one()
    customer = db.query(Customer).filter_by(id=identity.customer_id).with_for_update().populate_existing().first()
    if not customer or not eligible(customer) or customer.tenant_id != identity.tenant_id:
        raise HTTPException(403, "Původní účet předplatného již není dostupný.")
    assert_account_owner(db, identity)
    token_id = fingerprint(token, cfg)
    row = db.get(GoogleSubscription, token_id)
    if row and row.account_token != identity.token:
        raise HTTPException(403, "Tento nákup patří jinému účtu Evidence Vozidel.")
    client = publisher(cfg)
    data = client.get(token)
    values = snapshot(data, cfg)
    if values["test_purchase"] and identity.customer_id not in cfg.test_customer_ids:
        raise HTTPException(403, "Testovací nákup je povolen pouze vyhrazenému testovacímu účtu.")
    linked_token = data.get("linkedPurchaseToken")
    out_of_app = data.get("outOfAppPurchaseContext") or {}
    if not (data.get("externalAccountIdentifiers") or {}).get("obfuscatedExternalAccountId") and out_of_app:
        # Google keeps the previous account only in this authenticated context
        # for an unacknowledged out-of-app resubscribe after expiry.
        previous_token = out_of_app.get("expiredPurchaseToken")
        previous = db.get(GoogleSubscription, fingerprint(previous_token, cfg)) if previous_token else None
        expired_ids = out_of_app.get("expiredExternalAccountIdentifiers") or {}
        if not previous or previous.account_token != identity.token or expired_ids.get("obfuscatedExternalAccountId") != identity.token:
            raise HTTPException(403, "Obnovený nákup nelze přiřadit k původnímu účtu.")
    else:
        _owner_matches(data, identity, row)
    # Follow a bounded linked chain. Even an unused intermediate purchase must
    # match the original account; link records survive account erasure.
    ancestors, seen = [], {token_id}
    while linked_token:
        linked_id = fingerprint(linked_token, cfg)
        if linked_id in seen or len(ancestors) >= 8:
            raise HTTPException(400, "Řetězec nákupu u Google Play není platný.")
        seen.add(linked_id)
        previous = db.get(GoogleSubscription, linked_id)
        if previous:
            if previous.account_token != identity.token:
                raise HTTPException(403, "Předchozí nákup patří jinému účtu Evidence Vozidel.")
            # An intermediate token already superseded by another chain cannot
            # authorize a second unrelated replacement.
            if previous.superseded_by and previous.superseded_by not in seen:
                raise HTTPException(409, "Tento nákup byl již nahrazen jiným předplatným.")
            ancestors.append(previous)
            break
        prior_data = client.get(linked_token)
        prior_values = snapshot(prior_data, cfg)
        _owner_matches(prior_data, identity)
        previous = GoogleSubscription(id=linked_id, account_token=identity.token,
            encrypted_token=encrypt_token(linked_token, cfg, identity), package_name=cfg.package_name, **prior_values)
        db.add(previous); db.flush()
        ancestors.append(previous)
        linked_token = prior_data.get("linkedPurchaseToken")
    if other_paid_license(db, identity.tenant_id):
        raise HTTPException(409, "Účet již má placený tarif z jiného zdroje. Kontaktujte podporu.")
    if row is None:
        row = GoogleSubscription(id=token_id, account_token=identity.token,
            encrypted_token=encrypt_token(token, cfg, identity), package_name=cfg.package_name)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    row.verified_at = datetime.utcnow()
    row.linked_id = ancestors[0].id if ancestors else row.linked_id
    if row.superseded_by:
        row.active = False
    # Pending replacement does not revoke the still-paid predecessor.
    if row.active:
        for previous in ancestors:
            previous.active = False
            previous.auto_renew = False
            previous.superseded_by = row.id
    row.next_check_at = datetime.utcnow() + timedelta(minutes=15 if row.acknowledged else 1)
    row.failures = 0
    row.last_result = "verified"
    db.flush()
    apply_entitlement(db, identity)
    return row


def apply_entitlement(db, identity):
    if other_paid_license(db, identity.tenant_id):
        raise HTTPException(409, "Účet již má placený tarif z jiného zdroje.")
    rows = db.query(GoogleSubscription).filter_by(account_token=identity.token, active=True, superseded_by=None).filter(
        GoogleSubscription.expires_at > datetime.utcnow()).all()
    best = max(rows, key=lambda s: (s.plan == "premium", s.expires_at), default=None)
    # A hold/pause has no paid access, but Google may still resume billing.
    # Keep that obligation visible so another store cannot start a second charge.
    billing = best or db.query(GoogleSubscription).filter_by(account_token=identity.token, superseded_by=None).filter(
        GoogleSubscription.state.in_(["SUBSCRIPTION_STATE_PENDING", "SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"])
    ).order_by(GoogleSubscription.verified_at.desc()).first()
    sub = db.query(LicenseSubscription).filter_by(tenant_id=identity.tenant_id).first()
    if not billing and (not sub or sub.provider != "google"):
        return
    if sub is None:
        sub = LicenseSubscription(tenant_id=identity.tenant_id, provider="google")
        db.add(sub)
    sub.provider = "google"
    sub.plan_current = best.plan if best else "free"
    sub.status = ("grace" if best.state == "SUBSCRIPTION_STATE_IN_GRACE_PERIOD" else
                  "cancel_at_period_end" if not best.auto_renew else "active") if best else (
                    {"SUBSCRIPTION_STATE_PENDING": "pending", "SUBSCRIPTION_STATE_ON_HOLD": "on_hold",
                     "SUBSCRIPTION_STATE_PAUSED": "paused"}[billing.state] if billing else "canceled")
    sub.auto_renew_enabled = billing.auto_renew if billing else False
    sub.billing_period = billing.period if billing else sub.billing_period
    sub.current_period_end = billing.expires_at if billing else sub.current_period_end
    sub.last_trans_id = billing.id if billing else sub.last_trans_id
    sub.init_recurring_id = sub.next_charge_at = sub.pending_plan_change = None
    sub.grace_until = best.expires_at if best and sub.status == "grace" else None
    lic = db.query(License).filter_by(tenant_id=identity.tenant_id).first()
    if lic is None:
        lic = License(tenant_id=identity.tenant_id)
        db.add(lic)
    lic.plan, lic.status, lic.valid_to = sub.plan_current, "active", best.expires_at if best else None
    lic.vehicles_limit = PLAN_LIMITS[lic.plan]
    for flag in ("vin_decode_enabled", "ares_enabled", "reminders_enabled"):
        setattr(lic, flag, PLAN_FEATURES[lic.plan][flag])
    db.flush()


def acknowledge_committed(db, subscription_id, cfg):
    """Caller must commit synchronize() first; a failed ack is retried durably."""
    row = db.get(GoogleSubscription, subscription_id)
    if not row or row.acknowledged or not row.active or row.superseded_by:
        return False
    identity = db.get(GoogleBillingIdentity, row.account_token)
    if not identity or not identity.customer_id or not identity.tenant_id:
        return False
    try:
        publisher(cfg).acknowledge(row.product_id, decrypt_token(row, cfg), row.account_token)
    except HTTPException:
        row.next_check_at = datetime.utcnow() + timedelta(minutes=1)
        row.last_result = "ack_retry"
        db.commit()
        return True
    row.acknowledged = True
    row.last_result = "verified"
    db.commit()
    return False
