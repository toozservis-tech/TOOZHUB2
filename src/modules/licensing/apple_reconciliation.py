"""Recheck verified Apple purchases if notifications are delayed or missing.

Only Apple's signed, current API state can change access. This worker never
initiates a purchase, calls Comgate or sends customer messages. Each purchase has
a persistent lease/backoff, so a failing old purchase cannot starve newer ones.
"""
from datetime import datetime, timedelta, timezone
import os
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, inspect, or_
from sqlalchemy.exc import IntegrityError

from . import apple_store as store
from .apple_models import AppleBillingIdentity, AppleSubscription, AppleReconciliationState
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer

JOB_NAME = "apple.subscription.reconcile"
LEASE = timedelta(minutes=10)


def interval_seconds():
    try:
        return max(60, min(3600, int(os.getenv("APPLE_RECONCILIATION_INTERVAL_SEC", "300"))))
    except ValueError:
        return 300


def worker_enabled():
    return os.getenv("APPLE_IAP_ENABLED") == "1" and os.getenv(
        "ENABLE_APPLE_RECONCILIATION_WORKER", "1").lower() in {"1", "true", "yes", "on"}


def require_ready(db):
    cfg = store.config()
    store.require_schema(db)
    if not inspect(db.get_bind()).has_table(AppleReconciliationState.__tablename__):
        raise HTTPException(503, "Pravidelná kontrola App Storu čeká na dokončení nastavení databáze.")
    return cfg


def _candidates(db, cfg, now, limit):
    return [row[0] for row in db.query(AppleSubscription.id)
        .join(AppleBillingIdentity, AppleBillingIdentity.token == AppleSubscription.account_token)
        .join(Customer, Customer.id == AppleBillingIdentity.customer_id)
        .outerjoin(AppleReconciliationState, AppleReconciliationState.subscription_id == AppleSubscription.id)
        .filter(AppleSubscription.environment == cfg.environment.value,
                AppleBillingIdentity.tenant_id == Customer.tenant_id,
                Customer.is_deleted.isnot(True),
                or_(AppleReconciliationState.subscription_id.is_(None), AppleReconciliationState.next_check_at <= now))
        .order_by(func.coalesce(AppleReconciliationState.next_check_at, datetime(1970, 1, 1)), AppleSubscription.id)
        .limit(limit).all()]


def _claim(db, subscription_id, now):
    if db.get(AppleReconciliationState, subscription_id) is None:
        try:
            db.add(AppleReconciliationState(subscription_id=subscription_id, next_check_at=now))
            db.commit()
        except IntegrityError:
            # Another worker inserted the schedule, or the purchase was deleted.
            db.rollback()
    token = str(uuid4())
    changed = db.query(AppleReconciliationState).filter(
        AppleReconciliationState.subscription_id == subscription_id,
        AppleReconciliationState.next_check_at <= now).update({
            AppleReconciliationState.next_check_at: now + LEASE,
            AppleReconciliationState.claim_token: token,
            AppleReconciliationState.last_attempt_at: now,
            AppleReconciliationState.last_result: "checking",
        }, synchronize_session=False)
    db.commit()
    return token if changed == 1 else None


def _finish(db, subscription_id, claim, *, now, outcome, delay, failures):
    values = {AppleReconciliationState.next_check_at: now + delay,
              AppleReconciliationState.claim_token: None,
              AppleReconciliationState.last_result: outcome,
              AppleReconciliationState.failures: failures}
    if outcome == "verified":
        values[AppleReconciliationState.last_success_at] = now
    # A slow, expired claimant must not replace a newer worker's schedule.
    db.query(AppleReconciliationState).filter(
        AppleReconciliationState.subscription_id == subscription_id,
        AppleReconciliationState.claim_token == claim).update(values, synchronize_session=False)


def reconcile_subscriptions(*, session_factory=SessionLocal, batch_size=20, time_budget_seconds=60):
    result = {"checked": 0, "errors": 0, "skipped": 0, "available": True}
    with session_factory() as db:
        cfg = require_ready(db)
        ids = _candidates(db, cfg, datetime.utcnow(), max(1, min(100, batch_size)))
    deadline = time.monotonic() + max(1, min(300, time_budget_seconds))
    for subscription_id in ids:
        if time.monotonic() >= deadline:
            break  # Remaining purchases keep their place in the durable queue.
        with session_factory() as db:
            claim = _claim(db, subscription_id, datetime.utcnow())
            if claim is None:
                result["skipped"] += 1
                continue
            failures = db.get(AppleReconciliationState, subscription_id).failures
            try:
                row = db.get(AppleSubscription, subscription_id)
                identity = db.get(AppleBillingIdentity, row.account_token) if row else None
                customer = db.get(Customer, identity.customer_id) if identity and identity.customer_id else None
                if not customer or customer.is_deleted or not identity.tenant_id or identity.tenant_id != customer.tenant_id:
                    _finish(db, subscription_id, claim, now=datetime.utcnow(), outcome="account_removed",
                            delay=timedelta(days=1), failures=0)
                    db.commit()
                    result["skipped"] += 1
                    continue
                store.synchronize(db, identity, row.original_transaction_id, cfg)
                db.refresh(row)
                # Pending renewals/grace are checked often; old inactive purchases
                # still get checked for refund reversals without flooding Apple.
                delay = timedelta(minutes=15) if row.active or row.auto_renew or row.status == 3 else timedelta(days=1)
                _finish(db, subscription_id, claim, now=datetime.utcnow(), outcome="verified", delay=delay, failures=0)
                db.commit()
                result["checked"] += 1
            except Exception:
                # Roll back all entitlement mutations before persisting the retry.
                # Never put exception details/JWS/keys in a user-visible result.
                db.rollback()
                failures = min(failures + 1, 12)
                _finish(db, subscription_id, claim, now=datetime.utcnow(), outcome="retry",
                        delay=timedelta(minutes=min(360, 5 * 2 ** (failures - 1))), failures=failures)
                db.commit()
                result["errors"] += 1
    return result


def reconciliation_summary(db):
    """Aggregate operational status, with no customer or transaction identifiers."""
    require_ready(db)
    cfg = store.config()
    rows = db.query(AppleReconciliationState).join(AppleSubscription).join(AppleBillingIdentity).filter(
        AppleSubscription.environment == cfg.environment.value,
        AppleBillingIdentity.customer_id.isnot(None), AppleBillingIdentity.tenant_id.isnot(None))
    last_success = rows.with_entities(func.max(AppleReconciliationState.last_success_at)).scalar()
    return {
        "last_success_at": last_success.replace(tzinfo=timezone.utc) if last_success else None,
        "retry_count": rows.filter(AppleReconciliationState.last_result == "retry").count(),
        "due_count": len(_candidates(db, cfg, datetime.utcnow(), 1000)),
        "due_count_capped": True,
    }
