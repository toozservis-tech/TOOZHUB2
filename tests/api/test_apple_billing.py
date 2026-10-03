"""Isolated Apple lifecycle/security checks. No real purchase, account or remote API."""
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier, VerificationException

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, License, LicenseSubscription, LicensePaymentTransaction
from src.modules.licensing import apple_store as store
from src.modules.licensing.apple_models import AppleBillingIdentity, AppleSubscription
from src.modules.licensing.service import get_or_create_license
from src.modules.vehicle_hub.routers_v1 import apple_billing as api, license_status as comgate


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Tenant(id=31, name="Apple test", license_key="apple-fixture"))
    db.flush()
    user = Customer(id=31, tenant_id=31, name="Fixture", email="apple@example.invalid", role="user")
    db.add(user); db.flush()
    db.add(License(tenant_id=31, plan="free", status="active", vehicles_limit=1))
    identity = store.identity_for_user(db, user)
    db.commit()
    cfg = store.AppleConfig("cz.toozservis.spravavozidel.ios", 123456, "123", Environment.PRODUCTION, "key", "issuer", "fixture")
    monkeypatch.setattr(store, "config", lambda: cfg)
    monkeypatch.setattr(comgate, "_ensure_subscription_schema", lambda *a, **k: True)
    yield db, user, identity, cfg
    db.close(); engine.dispose()


def signed_state(setup, monkeypatch, *, plan="basic", state=1, expiry=None, grace=None, signed=None, **changes):
    db, user, identity, cfg = setup
    now = datetime.utcnow()
    ms = lambda d: int((d - datetime(1970, 1, 1)).total_seconds() * 1000)
    values = dict(originalTransactionId="original-1", transactionId="transaction-1", bundleId=cfg.bundle_id,
        environment=cfg.environment, productId=f"cz.toozservis.spravavozidel.{plan}.monthly",
        subscriptionGroupIdentifier=cfg.group_id, type="Auto-Renewable Subscription", inAppOwnershipType="PURCHASED",
        appAccountToken=identity.token, expiresDate=ms(expiry or now + timedelta(days=30)),
        signedDate=signed or ms(now), revocationDate=None, isUpgraded=False)
    values.update(changes)
    tx = NS(**values)
    renewal = NS(originalTransactionId=tx.originalTransactionId, environment=cfg.environment,
        appAccountToken=identity.token, gracePeriodExpiresDate=ms(grace) if grace else None,
        signedDate=tx.signedDate, autoRenewStatus=1)
    item = NS(originalTransactionId=tx.originalTransactionId, signedTransactionInfo="tx", signedRenewalInfo="renewal", status=state)
    response = NS(bundleId=cfg.bundle_id, environment=cfg.environment, appAppleId=cfg.app_id,
                  data=[NS(subscriptionGroupIdentifier=cfg.group_id, lastTransactions=[item])])
    verifier = NS(verify_and_decode_signed_transaction=lambda _: tx, verify_and_decode_renewal_info=lambda _: renewal)
    client = NS(get_all_subscription_statuses=lambda _: response)
    monkeypatch.setattr(store, "apple_services", lambda _: (verifier, client))
    return tx, renewal, response


def sync(setup):
    db, _, identity, cfg = setup
    store.synchronize(db, identity, "original-1", cfg)
    db.commit()
    return db.query(License).one(), db.query(LicenseSubscription).first()


def test_verified_purchase_and_duplicate_grant_once(setup, monkeypatch):
    signed_state(setup, monkeypatch)
    license, sub = sync(setup)
    end = license.valid_to
    assert license.plan == "basic" and sub.provider == "apple"
    assert sub.next_charge_at is None and sub.init_recurring_id is None
    sync(setup)
    assert setup[0].query(AppleSubscription).count() == 1
    assert license.valid_to == end


@pytest.mark.parametrize("changes", [dict(bundleId="wrong"), dict(environment=Environment.SANDBOX),
    dict(productId="unknown"), dict(subscriptionGroupIdentifier="other"), dict(type="Consumable"),
    dict(inAppOwnershipType="FAMILY_SHARED"), dict(appAccountToken=str(uuid4())), dict(appAccountToken=None),
    dict(originalTransactionId="wrong-original"), dict(expiresDate=-1), dict(signedDate=99999999999999)])
def test_wrong_app_environment_owner_or_metadata_never_unlocks(setup, monkeypatch, changes):
    signed_state(setup, monkeypatch, **changes)
    with pytest.raises(HTTPException): sync(setup)
    assert setup[0].query(License).one().plan == "free"
    assert setup[0].query(AppleSubscription).count() == 0


@pytest.mark.parametrize("state,changes", [(5, dict(revocationDate=1)), (2, {}), (3, {}), (1, dict(isUpgraded=True))])
def test_refund_expiry_retry_upgrade_remove_access(setup, monkeypatch, state, changes):
    signed_state(setup, monkeypatch); sync(setup)
    signed_state(setup, monkeypatch, state=state, **changes)
    license, sub = sync(setup)
    assert license.plan == "free" and sub.status == "canceled"


def test_grace_has_bounded_access_and_late_notification_cannot_extend_it(setup, monkeypatch):
    signed_state(setup, monkeypatch, state=4, expiry=datetime.utcnow()-timedelta(days=1), grace=datetime.utcnow()+timedelta(days=2))
    license, sub = sync(setup)
    assert license.plan == "basic" and sub.status == "grace"
    license.valid_to = datetime.utcnow()-timedelta(seconds=1)
    setup[0].commit()
    assert get_or_create_license(setup[0], 31).plan == "free"


def test_stale_snapshot_cannot_restore_refunded_access(setup, monkeypatch):
    tx, _, _ = signed_state(setup, monkeypatch)
    stamp = tx.signedDate
    signed_state(setup, monkeypatch, state=5, revocationDate=1, signed=stamp+10)
    sync(setup)
    signed_state(setup, monkeypatch, signed=stamp)
    license, _ = sync(setup)
    assert license.plan == "free"


def test_other_provider_not_overwritten_and_session_blocks_second_purchase(setup, monkeypatch):
    db, user, identity, cfg = setup
    db.query(License).one().plan = "premium"; db.commit()
    assert api.purchase_session(user, db)["can_purchase"] is False
    signed_state(setup, monkeypatch)
    with pytest.raises(HTTPException) as exc: sync(setup)
    assert exc.value.status_code == 409
    db.rollback()
    assert db.query(License).one().plan == "premium"
    assert db.query(AppleSubscription).count() == 0


def test_comgate_controls_cannot_change_apple_subscription(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    db, user, *_ = setup
    for action in (comgate.cancel_subscription_endpoint, comgate.resume_subscription_endpoint):
        with pytest.raises(HTTPException) as error: action(user, db)
        assert error.value.status_code == 409
    assert db.query(LicenseSubscription).one().auto_renew_enabled


def test_unavailable_apple_api_retains_previous_verified_state(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    def unavailable(*_): raise RuntimeError("SECRET upstream details")
    monkeypatch.setattr(store, "apple_services", lambda _: (None, NS(get_all_subscription_statuses=unavailable)))
    with pytest.raises(HTTPException) as error: sync(setup)
    assert error.value.status_code == 503 and "SECRET" not in error.value.detail
    assert setup[0].query(License).one().plan == "basic"


def test_deleted_customer_keeps_only_unclaimable_identity(setup):
    db, user, identity, cfg = setup
    token = identity.token
    db.query(Customer).filter_by(id=user.id).delete(synchronize_session=False)
    db.commit(); db.expire_all()
    assert db.get(AppleBillingIdentity, token).customer_id is None


def test_pinned_apple_verifier_rejects_forged_jws(setup):
    from pathlib import Path
    roots = [p.read_bytes() for p in (Path(store.__file__).parent / "apple_roots").glob("*.cer")]
    cfg = setup[3]
    verifier = SignedDataVerifier(roots, True, cfg.environment, cfg.bundle_id, cfg.app_id)
    with pytest.raises(VerificationException):
        verifier.verify_and_decode_signed_transaction("eyJhbGciOiJub25lIn0.eyJwcm9kdWN0SWQiOiJwcmVtaXVtIn0.")


def test_disabled_config_never_contacts_apple(monkeypatch):
    monkeypatch.delenv("APPLE_IAP_ENABLED", raising=False)
    with pytest.raises(HTTPException) as exc: store.config()
    assert exc.value.status_code == 503


def test_real_apple_sdk_accepts_private_key_from_environment_text(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    import requests

    # Generated test-only key; never use credentials or contact Apple's API here.
    private_key = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("utf-8")
    cfg = store.AppleConfig("fixture.bundle", 123456, "fixture-group", Environment.PRODUCTION,
                            "fixture-key", str(uuid4()), private_key)
    monkeypatch.setattr(requests.Session, "request", lambda *_a, **_k: pytest.fail("Must remain offline"))
    store.apple_services.cache_clear()
    try:
        verifier, client = store.apple_services(cfg)
        assert isinstance(verifier, SignedDataVerifier)
        assert isinstance(client, store.AppStoreServerAPIClient)
    finally:
        store.apple_services.cache_clear()


def test_pending_web_checkout_prevents_a_second_apple_charge(setup):
    db, user, *_ = setup
    db.add(LicensePaymentTransaction(tenant_id=user.tenant_id, provider="comgate", provider_status="PENDING"))
    db.commit()
    assert api.purchase_session(user, db)["can_purchase"] is False


def test_other_account_in_shared_tenant_cannot_replace_subscription(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    db, user, *_ = setup
    other = Customer(id=32, tenant_id=user.tenant_id, name="Other", email="other@example.invalid", role="user")
    db.add(other); db.commit()
    with pytest.raises(HTTPException) as exc: api.purchase_session(other, db)
    assert exc.value.status_code == 409
    assert db.query(License).one().plan == "basic"


def test_migration_is_additive_and_repeatable(setup):
    from scripts.migrate_apple_billing import migrate
    db, *_ = setup
    migrate(db.get_bind()); migrate(db.get_bind())
    assert db.query(Customer).count() == 1
    assert db.query(License).one().plan == "free"


def test_signed_webhook_refreshes_current_status_instead_of_trusting_event_order(setup, monkeypatch):
    tx, renewal, _ = signed_state(setup, monkeypatch, state=5, revocationDate=1)
    verifier, client = store.apple_services(setup[3])
    # Even an old DID_RENEW event is reconciled against the current refunded state.
    verifier.verify_and_decode_notification = lambda _: NS(notificationType="DID_RENEW", data=NS(signedTransactionInfo="old"))
    api.notifications(api.Notification(signedPayload="signed-fixture"), setup[0])
    assert setup[0].query(License).one().plan == "free"
    assert setup[0].query(AppleSubscription).one().status == 5


def test_deleted_account_notification_does_not_recreate_account(setup, monkeypatch):
    signed_state(setup, monkeypatch)
    db, user, identity, cfg = setup
    verifier, client = store.apple_services(cfg)
    verifier.verify_and_decode_notification = lambda _: NS(notificationType="DID_RENEW", data=NS(signedTransactionInfo="tx"))
    client.get_all_subscription_statuses = lambda _: pytest.fail("Deleted account must not be renewed")
    identity.customer_id = None; db.commit()
    assert api.notifications(api.Notification(signedPayload="signed-fixture"), db) == {"received": True}
    assert db.query(AppleSubscription).count() == 0


def test_renewal_mismatch_rejected(setup, monkeypatch):
    _, renewal, _ = signed_state(setup, monkeypatch)
    renewal.originalTransactionId = "foreign"
    with pytest.raises(HTTPException) as exc: sync(setup)
    assert exc.value.status_code == 400
    assert setup[0].query(License).one().plan == "free"
