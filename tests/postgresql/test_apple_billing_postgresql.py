"""Real isolated PostgreSQL locking; Apple responses are synthetic, never purchases."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace as NS

from fastapi import HTTPException
from appstoreserverlibrary.models.Environment import Environment

from src.modules.vehicle_hub.models import Customer, Tenant, License, LicenseSubscription
from src.modules.licensing import apple_store as store
from src.modules.licensing.apple_models import AppleBillingIdentity, AppleSubscription


def seed(pg_db):
    with pg_db.sessions() as db:
        db.add(Tenant(id=31, name="Synthetic Apple locking audit", license_key="apple-pg-fixture"))
        db.flush()
        db.add_all([Customer(id=number, tenant_id=31, name="Synthetic fixture",
                             email=f"apple-pg-{number}@example.invalid", role="user")
                    for number in (31, 32)])
        db.add(License(tenant_id=31, plan="free", status="active", vehicles_limit=1))
        db.commit()


def configuration():
    return store.AppleConfig("cz.toozservis.spravavozidel.ios", 123456, "123",
                             Environment.PRODUCTION, "fixture", "fixture", "fixture")


def state(cfg, token, original, *, stamp, revoked=False):
    expiry = datetime.utcnow() + timedelta(days=30)
    milliseconds = lambda value: int((value - datetime(1970, 1, 1)).total_seconds() * 1000)
    tx = NS(originalTransactionId=original, transactionId=f"{original}-{stamp}",
            bundleId=cfg.bundle_id, environment=cfg.environment,
            productId="cz.toozservis.spravavozidel.basic.monthly",
            subscriptionGroupIdentifier=cfg.group_id, type="Auto-Renewable Subscription",
            inAppOwnershipType="PURCHASED", appAccountToken=token,
            expiresDate=milliseconds(expiry), signedDate=stamp,
            revocationDate=stamp if revoked else None, isUpgraded=False)
    renewal = NS(originalTransactionId=original, environment=cfg.environment,
                 appAccountToken=token, gracePeriodExpiresDate=None,
                 signedDate=stamp, autoRenewStatus=1)
    response = NS(bundleId=cfg.bundle_id, environment=cfg.environment, appAppleId=cfg.app_id,
                  data=[NS(subscriptionGroupIdentifier=cfg.group_id,
                           lastTransactions=[NS(originalTransactionId=original,
                                                signedTransactionInfo=original,
                                                signedRenewalInfo=original,
                                                status=5 if revoked else 1)])])
    return tx, renewal, response


def test_concurrent_purchase_sessions_keep_one_token_for_same_customer(pg_db):
    seed(pg_db)
    ready = Barrier(2)

    def create_token():
        with pg_db.sessions() as db:
            user = db.get(Customer, 31)
            ready.wait(timeout=10)
            token = store.identity_for_user(db, user).token
            db.commit()
            return token

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create_token) for _ in range(2)]
        tokens = [future.result(timeout=20) for future in futures]
    assert tokens[0] == tokens[1]
    with pg_db.sessions() as db:
        assert db.query(AppleBillingIdentity).count() == 1
        assert db.query(License).one().plan == "free"


def test_concurrent_different_customer_purchases_cannot_claim_same_organization(pg_db, monkeypatch):
    seed(pg_db)
    cfg = configuration()
    with pg_db.sessions() as db:
        tokens = {number: store.identity_for_user(db, db.get(Customer, number)).token for number in (31, 32)}
        db.commit()
    stamp = int(datetime.utcnow().timestamp() * 1000)
    snapshots = {str(number): state(cfg, token, str(number), stamp=stamp) for number, token in tokens.items()}
    ready = Barrier(2)

    def fetch(original):
        ready.wait(timeout=10)  # Both Apple replies arrive before the entitlement lock.
        return snapshots[original][2]

    verifier = NS(verify_and_decode_signed_transaction=lambda value: snapshots[value][0],
                  verify_and_decode_renewal_info=lambda value: snapshots[value][1])
    monkeypatch.setattr(store, "apple_services", lambda _: (verifier, NS(get_all_subscription_statuses=fetch)))

    def purchase(number):
        with pg_db.sessions() as db:
            try:
                store.synchronize(db, db.get(AppleBillingIdentity, tokens[number]), str(number), cfg)
                db.commit()
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(purchase, number) for number in (31, 32)]
        outcomes = [future.result(timeout=20) for future in futures]
    assert sorted(outcomes) == [200, 409]
    with pg_db.sessions() as db:
        assert db.query(AppleSubscription).count() == 1
        assert db.query(LicenseSubscription).count() == 1
        assert db.query(License).one().plan == "basic"
        subscription = db.query(LicenseSubscription).one()
        assert subscription.provider == "apple"
        assert subscription.next_charge_at is None


def test_concurrent_old_reply_cannot_restore_refunded_entitlement(pg_db, monkeypatch):
    seed(pg_db)
    cfg = configuration()
    with pg_db.sessions() as db:
        token = store.identity_for_user(db, db.get(Customer, 31)).token
        db.commit()
    stamp = int(datetime.utcnow().timestamp() * 1000)
    # Separate fake response keys represent two overlapping reads for the same purchase.
    snapshots = {"active": state(cfg, token, "original", stamp=stamp),
                 "refunded": state(cfg, token, "original", stamp=stamp + 1, revoked=True)}
    # Refund races concern an already granted purchase. With a refund as the
    # first-ever event there need not be a LicenseSubscription row at all.
    initial = snapshots["active"]
    initial_verifier = NS(verify_and_decode_signed_transaction=lambda _: initial[0],
                          verify_and_decode_renewal_info=lambda _: initial[1])
    monkeypatch.setattr(store, "apple_services", lambda _: (initial_verifier,
                        NS(get_all_subscription_statuses=lambda _: initial[2])))
    with pg_db.sessions() as db:
        store.synchronize(db, db.get(AppleBillingIdentity, token), "original", cfg)
        db.commit()
        assert db.query(License).one().plan == "basic"
    ready = Barrier(2)
    from threading import local
    current = local()

    def fetch(_):
        ready.wait(timeout=10)
        return snapshots[current.kind][2]

    verifier = NS(verify_and_decode_signed_transaction=lambda _: snapshots[current.kind][0],
                  verify_and_decode_renewal_info=lambda _: snapshots[current.kind][1])
    monkeypatch.setattr(store, "apple_services", lambda _: (verifier, NS(get_all_subscription_statuses=fetch)))

    def synchronize(kind):
        current.kind = kind
        with pg_db.sessions() as db:
            store.synchronize(db, db.get(AppleBillingIdentity, token), "original", cfg)
            db.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(synchronize, kind) for kind in ("active", "refunded")]
        for future in futures:
            future.result(timeout=20)
    with pg_db.sessions() as db:
        assert db.query(AppleSubscription).one().status == 5
        assert db.query(AppleSubscription).one().active is False
        assert db.query(License).one().plan == "free"
        assert db.query(LicenseSubscription).one().auto_renew_enabled is False
