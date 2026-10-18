"""Isolated Google Play contract, lifecycle and ownership tests. No remote purchases."""
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
import json
from types import SimpleNamespace

from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, License, LicenseSubscription, LicensePaymentTransaction
from src.modules.licensing import google_store as store, google_reconciliation as worker, apple_store
from src.modules.licensing.google_models import GoogleBillingIdentity, GoogleSubscription
from src.modules.licensing.service import get_or_create_license
from src.modules.vehicle_hub.routers_v1 import google_billing as api, license_status as comgate, mobile_billing
REAL_CONFIG = store.config

TOKEN = "purchase-token-fixture-1"
SECOND = "purchase-token-fixture-2"
REQUEST = Request({"type": "http", "method": "POST", "path": "/license/google/sync", "headers": []})


def date(value):
    return value.isoformat() + "Z"


def purchase(identity, *, plan="basic", period="monthly", state="ACTIVE", expiry=None, **changes):
    data = dict(kind="androidpublisher#subscriptionPurchaseV2", subscriptionState="SUBSCRIPTION_STATE_" + state,
        acknowledgementState="ACKNOWLEDGEMENT_STATE_PENDING",
        externalAccountIdentifiers={"obfuscatedExternalAccountId": identity.token},
        lineItems=[dict(productId="evidence_vozidel_" + plan, expiryTime=date(expiry or datetime.utcnow() + timedelta(days=30)),
                       latestSuccessfulOrderId="GPA-fixture", autoRenewingPlan={"autoRenewEnabled": state != "CANCELED"},
                       offerDetails={"basePlanId": period})])
    data.update(changes)
    return data


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    db.add(Tenant(id=31, name="Fixture", license_key="google-fixture")); db.flush()
    user = Customer(id=31, tenant_id=31, name="Fixture", email="google@example.invalid", role="user")
    db.add(user); db.flush()
    db.add(License(tenant_id=31, plan="free", status="active", vehicles_limit=1))
    identity = store.identity_for_user(db, user); db.commit()
    cfg = store.GoogleConfig(store.PACKAGE_NAME, "fixture", Fernet.generate_key().decode(),
                            push_audience="https://api.example.invalid/api/v1/license/google/notifications",
                            push_service_account="push@example.iam.gserviceaccount.com")
    data, acks, calls = {}, [], []
    def get(token):
        calls.append(token)
        value = data[token]
        if isinstance(value, Exception):
            raise value
        return deepcopy(value)
    def acknowledge(product, token, account):
        # A durable license must exist before a server tells Google to keep payment.
        with factory() as check:
            assert check.query(License).filter_by(tenant_id=31).one().plan != "free"
        acks.append((product, token, account))
        if data.get("ack_failure"):
            raise HTTPException(503, "unavailable")
    monkeypatch.setattr(store, "publisher", lambda _: SimpleNamespace(get=get, acknowledge=acknowledge))
    monkeypatch.setattr(store, "config", lambda: cfg)
    monkeypatch.setattr(api, "limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(comgate, "_ensure_subscription_schema", lambda *args, **kwargs: True)
    result = SimpleNamespace(db=db, user=user, identity=identity, cfg=cfg, data=data, acks=acks, calls=calls,
                             factory=factory, engine=engine)
    yield result
    db.close(); engine.dispose()


def sync(s, token=TOKEN):
    return api.sync_purchase(api.Purchase(purchase_token=token), REQUEST, s.user, s.db)


def test_verified_purchase_idempotent_encrypted_and_acknowledged_after_commit(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity)
    result = sync(s)
    assert result["verified"] and not result["acknowledgement_pending"]
    assert result["plan"] == "basic" and result["provider"] == "google" and result["auto_renew"]
    row = s.db.query(GoogleSubscription).one()
    assert TOKEN not in row.encrypted_token and store.decrypt_token(row, s.cfg) == TOKEN
    assert row.id != TOKEN and len(row.id) == 64
    s.data[TOKEN]["acknowledgementState"] = "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"
    sync(s)
    assert s.db.query(GoogleSubscription).count() == 1 and len(s.acks) == 1
    sub = s.db.query(LicenseSubscription).one()
    assert sub.next_charge_at is None and sub.init_recurring_id is None


@pytest.mark.parametrize("state,active", [("ACTIVE", True), ("IN_GRACE_PERIOD", True), ("CANCELED", True),
    ("PENDING", False), ("ON_HOLD", False), ("PAUSED", False), ("EXPIRED", False), ("PENDING_PURCHASE_CANCELED", False)])
def test_lifecycle_states_only_grant_verified_paid_access(setup, state, active):
    s = setup; s.data[TOKEN] = purchase(s.identity, state=state)
    result = sync(s)
    assert (result["plan"] == "basic") == active
    assert bool(s.acks) == active
    if state == "CANCELED":
        assert not result["auto_renew"] and result["status"] == "cancel_at_period_end"
    if state == "IN_GRACE_PERIOD":
        assert result["status"] == "grace"


@pytest.mark.parametrize("state", ["EXPIRED", "ON_HOLD", "PAUSED", "PENDING_PURCHASE_CANCELED"])
def test_revoke_refund_or_hold_removes_previous_access(setup, state):
    s = setup; s.data[TOKEN] = purchase(s.identity, plan="premium"); sync(s)
    s.data[TOKEN] = purchase(s.identity, plan="premium", state=state)
    assert sync(s)["plan"] == "free"


@pytest.mark.parametrize("bad", ["product", "baseplan", "offer", "prepaid", "kind", "state", "ack", "owner", "expiry", "test"])
def test_untrusted_product_owner_or_metadata_never_grants(setup, bad):
    s = setup; data = purchase(s.identity)
    if bad == "product": data["lineItems"][0]["productId"] = "arbitrary_product"
    if bad == "baseplan": data["lineItems"][0]["offerDetails"]["basePlanId"] = "lifetime"
    if bad == "offer": data["lineItems"][0]["offerDetails"]["offerId"] = "unreviewed_free_trial"
    if bad == "prepaid": data["lineItems"][0]["prepaidPlan"] = {}
    if bad == "kind": data["kind"] = "one_time_product"
    if bad == "state": data["subscriptionState"] = "bogus"
    if bad == "ack": data["acknowledgementState"] = "bogus"
    if bad == "owner": data["externalAccountIdentifiers"]["obfuscatedExternalAccountId"] = "other-account"
    if bad == "expiry": data["lineItems"][0]["expiryTime"] = "2026-10-18T10:00:00"  # No timezone.
    if bad == "test": data["testPurchase"] = {}
    s.data[TOKEN] = data
    with pytest.raises(HTTPException): sync(s)
    assert s.db.query(License).one().plan == "free" and s.db.query(GoogleSubscription).count() == 0


def test_expiry_is_enforced_even_if_google_unreachable(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    lic = s.db.query(License).one(); lic.valid_to = datetime.utcnow() - timedelta(seconds=1); s.db.commit()
    assert get_or_create_license(s.db, 31).plan == "free"
    assert s.db.query(LicenseSubscription).one().provider == "google"


def test_temp_failure_keeps_only_previously_verified_entitlement(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    expiry = s.db.query(License).one().valid_to
    s.data[TOKEN] = HTTPException(503, "unavailable")
    with pytest.raises(HTTPException): sync(s)
    assert s.db.query(License).one().plan == "basic" and s.db.query(License).one().valid_to == expiry


def test_ack_failure_is_durable_and_retried_by_worker(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); s.data["ack_failure"] = True
    assert sync(s)["acknowledgement_pending"]
    row = s.db.query(GoogleSubscription).one()
    assert not row.acknowledged and row.last_result == "ack_retry"
    row.next_check_at = datetime.utcnow() - timedelta(seconds=1); s.db.commit()
    s.data["ack_failure"] = False
    assert worker.reconcile_subscriptions(session_factory=s.factory)["checked"] == 1
    s.db.expire_all(); assert s.db.query(GoogleSubscription).one().acknowledged


def test_deferred_replacement_does_not_unlock_future_plan(setup):
    s = setup; data = purchase(s.identity)
    future = deepcopy(data["lineItems"][0]); future["productId"] = "evidence_vozidel_premium"
    future.pop("expiryTime"); future.pop("latestSuccessfulOrderId")
    data["lineItems"].append(future); s.data[TOKEN] = data
    assert sync(s)["plan"] == "basic"
    # Even an expiry on a not-yet-owned second item is insufficient.
    future["expiryTime"] = date(datetime.utcnow() + timedelta(days=365))
    assert sync(s)["plan"] == "basic"


def test_upgrade_then_refund_cannot_resurrect_predecessor(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    s.data[SECOND] = purchase(s.identity, plan="premium", linkedPurchaseToken=TOKEN)
    assert sync(s, SECOND)["plan"] == "premium"
    assert not s.db.get(GoogleSubscription, store.fingerprint(TOKEN, s.cfg)).active
    s.data[SECOND] = purchase(s.identity, plan="premium", state="EXPIRED", linkedPurchaseToken=TOKEN)
    assert sync(s, SECOND)["plan"] == "free"
    assert sync(s, TOKEN)["plan"] == "free"


def test_pending_replacement_keeps_old_paid_plan(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    s.data[SECOND] = purchase(s.identity, plan="premium", state="PENDING", linkedPurchaseToken=TOKEN)
    assert sync(s, SECOND)["plan"] == "basic"
    assert s.db.get(GoogleSubscription, store.fingerprint(TOKEN, s.cfg)).superseded_by is None


def test_linked_owner_cannot_be_changed_or_deleted_then_reclaimed(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    original = s.identity.token
    s.identity.customer_id = s.identity.tenant_id = None; s.db.commit()
    replacement = store.identity_for_user(s.db, s.user); s.db.commit()
    s.data[TOKEN] = purchase(replacement)
    s.data[SECOND] = purchase(replacement, plan="premium", linkedPurchaseToken=TOKEN)
    for token in (TOKEN, SECOND):
        with pytest.raises(HTTPException) as exc: sync(s, token)
        assert exc.value.status_code == 403
    assert s.db.get(GoogleSubscription, store.fingerprint(TOKEN, s.cfg)).account_token == original


def test_deleted_user_leaves_immutable_tombstone(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    token = s.identity.token
    s.db.query(Customer).filter_by(id=s.user.id).delete(synchronize_session=False); s.db.commit(); s.db.expire_all()
    assert s.db.get(GoogleBillingIdentity, token).customer_id is None
    with pytest.raises(HTTPException): store.synchronize(s.db, s.db.get(GoogleBillingIdentity, token), TOKEN, s.cfg)


def test_out_of_app_resubscribe_requires_expired_original_binding(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity, state="EXPIRED"); sync(s)
    context = {"expiredPurchaseToken": TOKEN, "expiredExternalAccountIdentifiers": {"obfuscatedExternalAccountId": s.identity.token}}
    s.data[SECOND] = purchase(s.identity, externalAccountIdentifiers={}, outOfAppPurchaseContext=context)
    assert sync(s, SECOND)["plan"] == "basic"
    s.data[SECOND]["outOfAppPurchaseContext"]["expiredExternalAccountIdentifiers"]["obfuscatedExternalAccountId"] = "other"
    with pytest.raises(HTTPException): sync(s, SECOND)


@pytest.mark.parametrize("provider", ["apple", "comgate", "manual"])
def test_existing_paid_provider_blocks_google_session_and_sync(setup, provider):
    s = setup; s.db.query(License).one().plan = "premium"
    s.db.add(LicenseSubscription(tenant_id=31, provider=provider, plan_current="premium", status="active",
        auto_renew_enabled=True, current_period_end=datetime.utcnow() + timedelta(days=30))); s.db.commit()
    assert api.purchase_session(s.user, s.db)["reason"] == "other_provider"
    s.data[TOKEN] = purchase(s.identity)
    with pytest.raises(HTTPException) as exc: sync(s)
    assert exc.value.status_code == 409 and s.db.query(LicenseSubscription).one().provider == provider


def test_google_blocks_apple_and_comgate_checkout_and_callback(setup, monkeypatch):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    assert apple_store.other_paid_license(s.db, 31)
    monkeypatch.setattr(comgate, "_load_comgate_config", lambda: {})
    with pytest.raises(HTTPException) as exc:
        mobile_billing._quote(mobile_billing.Selection(plan="basic"), s.user, s.db)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        comgate._activate_subscription_from_paid_payment(s.db, tenant_id=31, plan="premium", billing_period="monthly",
                                                        trans_id="callback", init_recurring_id="recurring")
    assert exc.value.status_code == 409 and s.db.query(LicenseSubscription).one().provider == "google"


def test_pending_comgate_checkout_blocks_google(setup):
    s = setup
    s.db.add(LicensePaymentTransaction(tenant_id=31, provider="comgate", provider_status="PENDING", event_type="checkout",
                                      plan="basic", billing_period="monthly", amount_halers=14900, currency="CZK"))
    s.db.commit()
    assert not api.purchase_session(s.user, s.db)["can_purchase"]


def test_test_purchase_needs_explicit_flag_and_account_allowlist(setup, monkeypatch):
    s = setup; s.data[TOKEN] = purchase(s.identity, testPurchase={})
    monkeypatch.setattr(store, "config", lambda: replace(s.cfg, allow_test_purchases=True))
    with pytest.raises(HTTPException): sync(s)
    monkeypatch.setattr(store, "config", lambda: replace(s.cfg, allow_test_purchases=True, test_customer_ids=frozenset({31})))
    assert sync(s)["plan"] == "basic"


def test_unknown_link_is_verified_not_trusted_from_client(setup):
    s = setup
    s.data[TOKEN] = purchase(s.identity); s.data[TOKEN]["externalAccountIdentifiers"] = {"obfuscatedExternalAccountId": "other"}
    s.data[SECOND] = purchase(s.identity, plan="premium", linkedPurchaseToken=TOKEN)
    with pytest.raises(HTTPException) as exc: sync(s, SECOND)
    assert exc.value.status_code == 403 and s.db.query(GoogleSubscription).count() == 0


def test_refresh_reconcile_uses_encrypted_server_tokens_and_is_throttled(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    assert api.reconcile(REQUEST, s.user, s.db)["checked"] == 0
    row = s.db.query(GoogleSubscription).one(); row.verified_at -= timedelta(minutes=5); s.db.commit()
    s.data[TOKEN] = purchase(s.identity, state="EXPIRED")
    assert api.reconcile(REQUEST, s.user, s.db)["plan"] == "free"


def test_worker_backoff_on_outage_preserves_verified_state(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    row = s.db.query(GoogleSubscription).one(); row.next_check_at = datetime.utcnow() - timedelta(minutes=1); s.db.commit()
    s.data[TOKEN] = HTTPException(503, "not available")
    assert worker.reconcile_subscriptions(session_factory=s.factory)["errors"] == 1
    s.db.expire_all(); row = s.db.query(GoogleSubscription).one()
    assert row.claim_token is None and row.failures == 1 and row.next_check_at > datetime.utcnow()
    assert s.db.query(License).one().plan == "basic"


def test_restore_deduplicates_and_rejects_foreign_token(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); s.data[SECOND] = purchase(s.identity)
    s.data[SECOND]["externalAccountIdentifiers"] = {"obfuscatedExternalAccountId": "other"}
    result = api.restore(api.Restore(purchase_tokens=[TOKEN, TOKEN, SECOND]), REQUEST, s.user, s.db)
    assert result["restored_count"] == 1 and result["rejected_count"] == 1 and result["plan"] == "basic"
    assert s.db.query(GoogleSubscription).count() == 1


def test_customer_role_and_preview_package_fail_closed(setup, monkeypatch):
    s = setup; s.user.role = "service"
    assert api.purchase_session(s.user, s.db)["reason"] == "account_ineligible"
    s.data[TOKEN] = purchase(s.identity)
    with pytest.raises(HTTPException): sync(s)


def test_api_contract_catalog_and_payload_do_not_accept_client_grant_fields(setup):
    s = setup; app = FastAPI(); app.include_router(api.router, prefix="/api/v1/license")
    app.dependency_overrides[api.get_current_user] = lambda: s.user
    app.dependency_overrides[get_db] = lambda: s.db
    with TestClient(app) as client:
        catalog = client.get("/api/v1/license/google/catalog").json()
        assert len(catalog["products"]) == 4 and catalog["package_name"] == store.PACKAGE_NAME
        session = client.post("/api/v1/license/google/session").json()
        assert session["can_purchase"] and len(session["obfuscated_account_id"]) == 64
        assert client.post("/api/v1/license/google/sync", json={"verified": True, "plan": "premium"}).status_code == 422
        s.data[TOKEN] = purchase(s.identity)
        response = client.post("/api/v1/license/google/sync", json={"purchase_token": TOKEN, "plan": "premium"})
        assert response.status_code == 200 and response.json()["plan"] == "basic"
        assert TOKEN not in response.text


def test_rtdn_signature_email_and_audience_checked(setup, monkeypatch):
    from google.oauth2 import id_token
    s = setup
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer fixture.jwt")]})
    claims = dict(email=s.cfg.push_service_account, email_verified=True, iss="https://accounts.google.com")
    def verify(token, transport, audience):
        assert token == "fixture.jwt" and audience == s.cfg.push_audience
        return claims
    monkeypatch.setattr(id_token, "verify_oauth2_token", verify)
    api.verify_push(request, s.cfg)
    for change in ({"email": "stranger"}, {"email_verified": False}, {"iss": "stranger"}):
        old = claims.copy(); claims.update(change)
        with pytest.raises(HTTPException): api.verify_push(request, s.cfg)
        claims.clear(); claims.update(old)


def test_rtdn_replays_read_current_google_state_not_event_state(setup, monkeypatch):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    monkeypatch.setattr(api, "verify_push", lambda *args: None)
    s.data[TOKEN] = purchase(s.identity, state="EXPIRED")
    body = {"packageName": store.PACKAGE_NAME, "subscriptionNotification": {"purchaseToken": TOKEN, "notificationType": 4}}
    envelope = {"message": {"data": base64.b64encode(json.dumps(body).encode()).decode()}}
    assert api.notifications(envelope, REQUEST, s.db) == {"received": True}
    assert api.notifications(envelope, REQUEST, s.db) == {"received": True}
    assert s.db.query(License).one().plan == "free"
    body["packageName"] += ".preview"; envelope["message"]["data"] = base64.b64encode(json.dumps(body).encode()).decode()
    with pytest.raises(HTTPException): api.notifications(envelope, REQUEST, s.db)


def test_additive_migration_repeated_preserves_accounts(setup):
    from scripts.migrate_google_billing import migrate
    s = setup; s.db.close()
    GoogleSubscription.__table__.drop(s.engine); GoogleBillingIdentity.__table__.drop(s.engine)
    migrate(s.engine); migrate(s.engine)
    assert s.db.get(Customer, 31).email == "google@example.invalid"
    assert s.db.query(License).one().plan == "free"


def test_deferred_switch_after_renewal_chooses_new_owned_item(setup):
    s = setup
    old = purchase(s.identity, plan="premium", expiry=datetime.utcnow() - timedelta(seconds=1))["lineItems"][0]
    data = purchase(s.identity, plan="basic"); data["lineItems"].insert(0, old); s.data[TOKEN] = data
    assert sync(s)["plan"] == "basic"


@pytest.mark.parametrize("state", ["ON_HOLD", "PAUSED", "PENDING"])
def test_no_access_but_google_payment_can_resume_blocks_another_store(setup, monkeypatch, state):
    s = setup; s.data[TOKEN] = purchase(s.identity, state=state, expiry=datetime.utcnow() - timedelta(days=1))
    assert sync(s)["plan"] == "free"
    assert apple_store.other_paid_license(s.db, 31)
    monkeypatch.setattr(comgate, "_load_comgate_config", lambda: {})
    with pytest.raises(HTTPException): mobile_billing._quote(mobile_billing.Selection(plan="basic"), s.user, s.db)
    assert s.db.query(LicenseSubscription).one().status in {"on_hold", "paused", "pending"}


def test_disabled_configuration_returns_safe_catalog_and_session(setup, monkeypatch):
    s = setup
    def disabled(): raise HTTPException(503, "Předplatné zatím není dostupné.")
    monkeypatch.setattr(store, "config", disabled)
    catalog = api.catalog(s.user, s.db); session = api.purchase_session(s.user, s.db)
    assert not catalog["enabled"] and catalog["products"] == []
    assert not session["can_purchase"] and session["reason"] == "not_configured"
    assert session["obfuscated_account_id"] is None


def test_actual_config_rejects_preview_and_arbitrary_oauth_endpoint(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLAY_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_PLAY_TOKEN_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", json.dumps(dict(type="service_account", private_key="fixture",
        client_email="test@example.iam.gserviceaccount.com", token_uri="https://oauth2.googleapis.com/token")))
    monkeypatch.setenv("GOOGLE_PLAY_PACKAGE_NAME", store.PACKAGE_NAME + ".preview")
    with pytest.raises(HTTPException) as exc: REAL_CONFIG()
    assert exc.value.status_code == 503
    monkeypatch.setenv("GOOGLE_PLAY_PACKAGE_NAME", store.PACKAGE_NAME)
    monkeypatch.setenv("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", json.dumps(dict(type="service_account", private_key="fixture",
        client_email="test@example.iam.gserviceaccount.com", token_uri="https://untrusted.invalid/token")))
    with pytest.raises(HTTPException): REAL_CONFIG()


def test_upstream_errors_never_expose_token_or_private_response():
    client = store.Publisher.__new__(store.Publisher)
    client.prefix = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/" + store.PACKAGE_NAME
    paths = []
    def request(method, path, **kwargs):
        paths.append(path)
        assert kwargs["timeout"] == (5, 20) and not kwargs["allow_redirects"]
        return SimpleNamespace(status_code=403, content=b"PRIVATE-CREDENTIAL-DIAGNOSTIC")
    client.session = SimpleNamespace(request=request)
    with pytest.raises(HTTPException) as exc: client.get(TOKEN)
    assert exc.value.status_code == 503 and TOKEN not in exc.value.detail and "PRIVATE" not in exc.value.detail
    assert paths[0].startswith("https://androidpublisher.googleapis.com/")


def test_missing_order_id_single_owned_promo_purchase_is_supported(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); del s.data[TOKEN]["lineItems"][0]["latestSuccessfulOrderId"]
    assert sync(s)["plan"] == "basic"


def test_encrypted_token_cannot_be_moved_to_different_identity(setup):
    s = setup; s.data[TOKEN] = purchase(s.identity); sync(s)
    row = s.db.query(GoogleSubscription).one(); row.account_token = "other"
    with pytest.raises(HTTPException): store.decrypt_token(row, s.cfg)
    s.db.rollback()
