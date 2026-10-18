"""Durable leased Google Play reconciliation; no customer messages or charges."""
from datetime import datetime, timedelta
import os
import time
from uuid import uuid4
from . import google_store as store
from .google_models import GoogleBillingIdentity, GoogleSubscription
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer


def worker_enabled():
    return os.getenv("GOOGLE_PLAY_ENABLED") == "1" and os.getenv("ENABLE_GOOGLE_RECONCILIATION_WORKER", "1") == "1"


def interval_seconds():
    return 60


def reconcile_subscriptions(*, session_factory=SessionLocal, batch_size=20, time_budget_seconds=50):
    cfg = store.config()
    now = datetime.utcnow()
    result = {"checked": 0, "errors": 0, "skipped": 0}
    with session_factory() as db:
        store.require_schema(db)
        ids = [value for value, in db.query(GoogleSubscription.id).join(GoogleBillingIdentity).join(
            Customer, Customer.id == GoogleBillingIdentity.customer_id).filter(
                GoogleSubscription.next_check_at <= now, GoogleSubscription.superseded_by.is_(None),
                GoogleSubscription.package_name == cfg.package_name,
                Customer.is_deleted.isnot(True), Customer.tenant_id == GoogleBillingIdentity.tenant_id).order_by(
                    GoogleSubscription.next_check_at, GoogleSubscription.id).limit(max(1, min(100, batch_size))).all()]
    deadline = time.monotonic() + max(1, min(300, time_budget_seconds))
    for subscription_id in ids:
        if time.monotonic() >= deadline:
            break
        with session_factory() as db:
            claim = str(uuid4())
            changed = db.query(GoogleSubscription).filter_by(id=subscription_id).filter(
                GoogleSubscription.next_check_at <= datetime.utcnow()).update({
                    "claim_token": claim, "next_check_at": datetime.utcnow() + timedelta(minutes=5)}, synchronize_session=False)
            db.commit()
            if not changed:
                result["skipped"] += 1
                continue
            row = db.get(GoogleSubscription, subscription_id)
            failures = row.failures or 0
            try:
                # Google stops serving an expired token after 60 days. It cannot
                # become a new subscription; a resubscribe receives a new token.
                if (not row.active and not row.auto_renew and row.expires_at and
                    row.expires_at < datetime.utcnow() - timedelta(days=60) and
                    row.state in {"SUBSCRIPTION_STATE_EXPIRED", "SUBSCRIPTION_STATE_CANCELED"}):
                    row.next_check_at = datetime(2099, 1, 1)
                    row.claim_token = None
                    row.last_result = "expired_retained"
                    db.commit()
                    result["skipped"] += 1
                    continue
                identity = db.get(GoogleBillingIdentity, row.account_token)
                store.synchronize(db, identity, store.decrypt_token(row, cfg), cfg)
                db.commit()
                pending = store.acknowledge_committed(db, subscription_id, cfg)
                db.refresh(row)
                delay = timedelta(minutes=1 if pending else 15) if row.active or row.auto_renew or row.state in {
                    "SUBSCRIPTION_STATE_PENDING", "SUBSCRIPTION_STATE_ON_HOLD", "SUBSCRIPTION_STATE_PAUSED"} else timedelta(days=1)
                values = dict(next_check_at=datetime.utcnow() + delay, claim_token=None, failures=0)
                result["checked"] += 1
            except Exception:
                db.rollback()
                failures = min(failures + 1, 12)
                values = dict(next_check_at=datetime.utcnow() + timedelta(minutes=min(360, 2 ** failures)),
                              claim_token=None, failures=failures, last_result="retry")
                result["errors"] += 1
            # Never let an old lease overwrite a newer worker's schedule.
            db.query(GoogleSubscription).filter_by(id=subscription_id, claim_token=claim).update(values, synchronize_session=False)
            db.commit()
    return result
