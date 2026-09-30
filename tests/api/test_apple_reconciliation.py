"""No live Apple API, payments or customer data; foreign keys remain enabled."""
from datetime import datetime, timedelta
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker
from appstoreserverlibrary.models.Environment import Environment

from test_apple_billing import setup, signed_state, sync
from src.modules.licensing import apple_store as store, apple_reconciliation as worker
from src.modules.licensing.apple_models import AppleSubscription, AppleReconciliationState
from src.modules.vehicle_hub.models import License, LicenseSubscription


def run(setup, **kwargs):
    return worker.reconcile_subscriptions(session_factory=sessionmaker(bind=setup[0].get_bind()), **kwargs)


def test_missed_renewal_is_recovered_and_schedule_persists(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    future = datetime.utcnow() + timedelta(days=60)
    signed_state(setup, monkeypatch, expiry=future, transactionId="next-renewal")
    assert run(setup)["checked"] == 1
    db = setup[0]; db.expire_all()
    assert abs((db.query(License).one().valid_to - future).total_seconds()) < 1
    schedule = db.query(AppleReconciliationState).one()
    assert schedule.last_result == "verified" and schedule.last_success_at
    assert schedule.claim_token is None and schedule.failures == 0
    assert run(setup)["checked"] == 0  # A fresh worker respects the database schedule.
    assert db.query(LicenseSubscription).one().next_charge_at is None


def test_missed_refund_removes_access_without_erasing_data(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    signed_state(setup, monkeypatch, state=5, revocationDate=1)
    assert run(setup)["checked"] == 1
    setup[0].expire_all()
    assert setup[0].query(License).one().plan == "free"
    assert setup[0].query(AppleSubscription).one().status == 5
    assert setup[1].email == "apple@example.invalid"


def test_failure_rolls_back_partial_changes_and_backs_off(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    def fail(db, *_):
        db.query(License).one().plan = "premium"
        db.flush()
        raise RuntimeError("SECRET key, JWS and upstream response")
    monkeypatch.setattr(store, "synchronize", fail)
    assert run(setup) == {"checked": 0, "errors": 1, "skipped": 0, "available": True}
    db = setup[0]; db.expire_all()
    assert db.query(License).one().plan == "basic"
    schedule = db.query(AppleReconciliationState).one()
    assert schedule.last_result == "retry" and schedule.failures == 1
    assert schedule.next_check_at > datetime.utcnow() + timedelta(minutes=4)
    assert schedule.last_success_at is None
    assert run(setup)["errors"] == 0
    schedule.next_check_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
    assert run(setup)["errors"] == 1
    db.expire_all()
    assert schedule.failures == 2 and schedule.next_check_at > datetime.utcnow() + timedelta(minutes=9)


def test_another_worker_cannot_claim_leased_purchase_and_expired_lease_recovers(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    Session = sessionmaker(bind=setup[0].get_bind())
    now = datetime.utcnow(); id = "Production:original-1"
    with Session() as first, Session() as second:
        first_claim = worker._claim(first, id, now)
        assert first_claim and worker._claim(second, id, now) is None
        next_claim = worker._claim(second, id, now + worker.LEASE + timedelta(seconds=1))
        assert next_claim and next_claim != first_claim
        worker._finish(first, id, first_claim, now=now, outcome="verified", delay=timedelta(days=1), failures=0)
        first.commit(); second.expire_all()
        assert second.get(AppleReconciliationState, id).claim_token == next_claim


@pytest.mark.parametrize("deleted", ["hard", "soft", "moved"])
def test_removed_account_is_never_renewed(setup, monkeypatch, deleted):
    signed_state(setup, monkeypatch); sync(setup)
    db, user, identity, _ = setup
    if deleted == "hard": identity.customer_id = None
    elif deleted == "soft": user.is_deleted = True
    else: identity.tenant_id = None
    db.commit()
    monkeypatch.setattr(store, "synchronize", lambda *_: pytest.fail("Removed account contacted Apple"))
    assert run(setup)["checked"] == 0
    assert db.query(AppleReconciliationState).count() == 0


def test_environment_does_not_fall_back(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    monkeypatch.setattr(store, "config", lambda: replace(setup[3], environment=Environment.SANDBOX))
    monkeypatch.setattr(store, "synchronize", lambda *_: pytest.fail("Production record used in sandbox"))
    assert run(setup)["checked"] == 0


def test_missing_schedule_migration_fails_closed(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    AppleReconciliationState.__table__.drop(setup[0].get_bind())
    with pytest.raises(HTTPException) as exc: run(setup)
    assert exc.value.status_code == 503
    from scripts.migrate_apple_billing import migrate
    migrate(setup[0].get_bind()); migrate(setup[0].get_bind())
    assert run(setup)["checked"] == 1


def test_disabled_integration_never_opens_apple_connection(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    def disabled(): raise HTTPException(503, "not configured")
    monkeypatch.setattr(store, "config", disabled)
    monkeypatch.setattr(store, "apple_services", lambda *_: pytest.fail("Unexpected Apple request"))
    with pytest.raises(HTTPException): run(setup)
    assert setup[0].query(AppleReconciliationState).count() == 0


def test_failed_old_purchase_does_not_starve_next_batch(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    signed_state(setup, monkeypatch, originalTransactionId="original-2")
    store.synchronize(setup[0], setup[2], "original-2", setup[3]); setup[0].commit()
    seen = []
    def fail_first(db, identity, original_id, cfg):
        seen.append(original_id)
        if original_id == "original-1": raise RuntimeError("Temporary problem")
    monkeypatch.setattr(store, "synchronize", fail_first)
    assert run(setup, batch_size=1)["errors"] == 1
    assert run(setup, batch_size=1)["checked"] == 1
    assert seen == ["original-1", "original-2"]


def test_summary_is_aggregate_and_does_not_expose_identity(setup, monkeypatch):
    signed_state(setup, monkeypatch); sync(setup)
    assert worker.reconciliation_summary(setup[0])["due_count"] == 1
    run(setup)
    summary = worker.reconciliation_summary(setup[0])
    assert summary["due_count"] == 0 and summary["last_success_at"]
    assert setup[2].token not in str(summary) and setup[1].email not in str(summary)


def test_deleted_while_apple_responds_cannot_get_access(setup, monkeypatch):
    signed_state(setup, monkeypatch)
    verifier, client = store.apple_services(setup[3])
    response = client.get_all_subscription_statuses("original-1")
    def current_state(_):
        setup[1].is_deleted = True
        setup[0].flush()
        return response
    client.get_all_subscription_statuses = current_state
    with pytest.raises(HTTPException) as exc: sync(setup)
    assert exc.value.status_code == 409
    assert setup[0].query(License).one().plan == "free"


def test_interval_and_enable_settings_are_bounded(monkeypatch):
    monkeypatch.setenv("APPLE_RECONCILIATION_INTERVAL_SEC", "broken")
    assert worker.interval_seconds() == 300
    monkeypatch.setenv("APPLE_RECONCILIATION_INTERVAL_SEC", "-3")
    assert worker.interval_seconds() == 60
    monkeypatch.setenv("APPLE_IAP_ENABLED", "0")
    assert not worker.worker_enabled()
    monkeypatch.setenv("APPLE_IAP_ENABLED", "1")
    monkeypatch.setenv("ENABLE_APPLE_RECONCILIATION_WORKER", "0")
    assert not worker.worker_enabled()
