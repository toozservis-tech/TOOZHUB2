"""Account-scoped referrals and additive Premium grants. No access or payment transfer."""
import calendar
import secrets
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, inspect, update
from fastapi import HTTPException
from .database import Base
from .models import Customer, ServiceRegistrationRequest, VehicleOwnership, License
from .email_verification import EmailVerification
from .service_job_models import ServiceJob


class ReferralCode(Base):
    __tablename__ = 'referral_codes'
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    code = Column(String(40), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Referral(Base):
    __tablename__ = 'referrals'
    id = Column(Integer, primary_key=True)
    referrer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, unique=True)
    service_request_id = Column(Integer, ForeignKey('service_registration_requests.id', ondelete='SET NULL'), nullable=True, unique=True)
    kind = Column(String(12), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    qualified_at = Column(DateTime, nullable=True)
    reason = Column(String(64), nullable=False, default='waiting_verification')


class ReferralReward(Base):
    __tablename__ = 'referral_rewards'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    client_id = Column(String(36), nullable=True, unique=True)
    source = Column(String(20), nullable=False)
    ordinal = Column(Integer, nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)  # NULL: explicit administrator lifetime grant
    granted_by = Column(Integer, ForeignKey('customers.id', ondelete='SET NULL'), nullable=True)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)
    waiting_for_paid = Column(Boolean, nullable=False, default=False, server_default='false')
    __table_args__ = (UniqueConstraint('customer_id', 'source', 'ordinal', name='uq_referral_reward_once'),)


TABLES = [ReferralCode.__table__, Referral.__table__, ReferralReward.__table__]


def ready(db):
    # Old releases keep working before this additive migration is deployed.
    schema = inspect(db.connection())
    return (all(schema.has_table(table.name) for table in TABLES)
            and 'waiting_for_paid' in {c['name'] for c in schema.get_columns('referral_rewards')})


def require_ready(db):
    if not ready(db):
        raise HTTPException(503, 'Pozvánky a odměny zatím nejsou na tomto serveru dostupné.')


def lock_referrer(db, customer_id):
    # SQLite FOR UPDATE is a no-op. Take its write lock before reading counters.
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(Customer).where(Customer.id == customer_id).values(id=Customer.id))
    else:
        db.query(Customer.id).filter_by(id=customer_id).with_for_update().one_or_none()


def code_for(db, customer):
    require_ready(db)
    lock_referrer(db, customer.id)
    row = db.get(ReferralCode, customer.id)
    if row is None:
        row = ReferralCode(customer_id=customer.id, code=secrets.token_urlsafe(18))
        db.add(row); db.flush()
    return row.code


def attach(db, code, *, customer=None, service_request=None):
    """Only called within NEW registration, not an editable account setting."""
    if not code:
        return
    require_ready(db)
    link = db.query(ReferralCode).filter_by(code=code).first()
    owner = db.get(Customer, link.customer_id) if link else None
    target = customer or service_request
    if not owner or owner.is_deleted or owner.is_disabled:
        raise HTTPException(422, 'Kód pozvánky není platný. Zkontrolujte jej nebo jej z registrace odeberte.')
    if owner.email.strip().lower() == target.email.strip().lower() or (customer and customer.id == owner.id):
        raise HTTPException(422, 'Vlastní účet nelze započítat jako pozvaného.')
    # A resubmitted workshop application keeps the first attribution.
    if service_request and db.query(Referral).filter_by(service_request_id=service_request.id).first():
        return
    db.add(Referral(referrer_id=owner.id, customer_id=customer.id if customer else None,
                    service_request_id=service_request.id if service_request else None,
                    kind='service' if service_request else 'user'))
    db.flush()


def next_month(value):
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def _target(db, row):
    if row.customer_id:
        return db.get(Customer, row.customer_id)
    request = db.get(ServiceRegistrationRequest, row.service_request_id) if row.service_request_id else None
    if request and request.status == 'approved' and request.approved_customer_id:
        return db.get(Customer, request.approved_customer_id)
    return None


def evaluate(db, referrer, now=None):
    """Serialized reconciliation on profile/license reads; retries never duplicate rewards.

    In the same transaction as the authenticated read, reconcile verified registrations
    and committed activity. A caller commits once, after all award rows are inserted.
    """
    if not ready(db) or referrer.is_deleted or referrer.is_disabled:
        return
    now = now or datetime.utcnow()
    lock_referrer(db, referrer.id)
    schedule_waiting_rewards(db, referrer, now)
    referrals = db.query(Referral).filter_by(referrer_id=referrer.id).populate_existing().order_by(Referral.id).all()
    for row in referrals:
        if row.qualified_at:
            continue
        target = _target(db, row)
        if not target:
            row.reason = 'waiting_service_approval' if row.kind == 'service' else 'unavailable'; continue
        if target.id == referrer.id or target.is_deleted or target.is_disabled:
            row.reason = 'ineligible'; continue
        if row.customer_id is None:
            # Do not permit a service role conversion to count the same account twice.
            duplicate = db.query(Referral.id).filter(Referral.customer_id == target.id, Referral.id != row.id).first()
            if duplicate: row.reason = 'ineligible'; continue
            row.customer_id = target.id
        verification = db.get(EmailVerification, target.id)
        if not verification or not verification.verified_at:
            row.reason = 'waiting_verification'; continue
        if row.kind == 'service':
            completed = target.role == 'service' and db.query(ServiceJob.id).filter(
                ServiceJob.service_id == target.id, ServiceJob.completed_at.isnot(None),
                ServiceJob.status == 'completed').first()
            row.reason = 'qualified' if completed else 'waiting_job'
        else:
            vehicle = target.role == 'user' and db.query(VehicleOwnership.id).filter(
                VehicleOwnership.customer_id == target.id, VehicleOwnership.is_active.is_(True),
                VehicleOwnership.ownership_type == 'owner').first()
            row.reason = 'qualified' if vehicle else 'waiting_vehicle'
        if row.reason == 'qualified': row.qualified_at = now
    db.flush()
    for kind, divisor in [('user', 3), ('service', 1)]:
        count = sum(r.kind == kind and r.qualified_at is not None for r in referrals) // divisor
        existing = {g.ordinal for g in db.query(ReferralReward).filter_by(customer_id=referrer.id, source=kind)}
        for ordinal in range(1, count + 1):
            if ordinal not in existing:
                grant(db, referrer, source=kind, ordinal=ordinal, reason='3 ověření uživatelé s vozidlem' if kind == 'user' else 'Ověřený servis s dokončenou zakázkou', now=now)



def evaluate_for_customer(db, customer_id):
    """Reconcile the inviter in the same transaction as a qualifying account action.

    Explicit event hooks cover email verification, vehicle creation/restoration and
    job completion. Profile/license reads also reconcile historical pending rows.
    No payment API or external network call is made here.
    """
    if not ready(db):
        return
    db.flush()
    ids = {row[0] for row in db.query(Referral.referrer_id).outerjoin(
        ServiceRegistrationRequest, Referral.service_request_id == ServiceRegistrationRequest.id
    ).filter((Referral.customer_id == customer_id) |
             (ServiceRegistrationRequest.approved_customer_id == customer_id)).all()}
    for referrer_id in sorted(ids):
        owner = db.get(Customer, referrer_id)
        if owner:
            evaluate(db, owner)



def schedule_waiting_rewards(db, customer, now):
    """Unused months earned during paid Premium do not expire while it renews."""
    paid = db.query(License).filter_by(tenant_id=customer.tenant_id).first()
    paid_active = bool(paid and paid.status == 'active' and paid.plan == 'premium'
                       and (not paid.valid_to or paid.valid_to > now))
    rows = db.query(ReferralReward).filter_by(customer_id=customer.id).filter(
        ReferralReward.revoked_at.is_(None)).order_by(ReferralReward.id).all()
    start = max([now] + [row.ends_at for row in rows if not row.waiting_for_paid and row.ends_at])
    if paid_active and paid.valid_to:
        start = max(start, paid.valid_to)
    for row in rows:
        if row.waiting_for_paid:
            row.starts_at, row.ends_at = start, next_month(start)
            row.waiting_for_paid = paid_active
            start = row.ends_at
    db.flush()


def grant(db, customer, *, source, ordinal, reason, now=None, actor=None, lifetime=False):
    now = now or datetime.utcnow()
    schedule_waiting_rewards(db, customer, now)
    start = now
    # A currently paid Premium period is not overwritten; queue the reward after it.
    paid = db.query(License).filter_by(tenant_id=customer.tenant_id).first()
    if paid and paid.status == 'active' and paid.plan == 'premium' and paid.valid_to and paid.valid_to > start:
        start = paid.valid_to
    pending = db.query(ReferralReward).filter(ReferralReward.customer_id == customer.id,
                                           ReferralReward.revoked_at.is_(None)).all()
    for reward in pending:
        if reward.ends_at and reward.ends_at > start: start = reward.ends_at
    waiting = bool(not lifetime and paid and paid.status == 'active' and paid.plan == 'premium'
                   and (not paid.valid_to or paid.valid_to > now))
    reward = ReferralReward(customer_id=customer.id, source=source, ordinal=ordinal, waiting_for_paid=waiting,
        starts_at=now if lifetime else start, ends_at=None if lifetime else next_month(start),
        granted_by=actor.id if actor else None, reason=reason)
    db.add(reward); db.flush()
    return reward


def active_reward(db, customer, now=None):
    if not customer or customer.is_deleted or customer.is_disabled or not ready(db): return None
    now = now or datetime.utcnow()
    return db.query(ReferralReward).filter(ReferralReward.customer_id == customer.id,
        ReferralReward.revoked_at.is_(None), ReferralReward.waiting_for_paid.is_(False), ReferralReward.starts_at <= now,
        (ReferralReward.ends_at.is_(None) | (ReferralReward.ends_at > now))).order_by(ReferralReward.ends_at.is_(None).desc(), ReferralReward.ends_at.desc()).first()


def effective_license(db, customer, paid):
    reward = active_reward(db, customer)
    # Never reactivate a suspended license/account or mutate the payment-ledger license.
    if not reward or paid.status != 'active': return paid
    if paid.plan == 'premium' and (not paid.valid_to or paid.valid_to > datetime.utcnow()): return paid
    fields = {column.key: getattr(paid, column.key) for column in License.__table__.columns}
    fields.update(plan='premium', vehicles_limit=0, valid_to=reward.ends_at,
                  vin_decode_enabled=True, ares_enabled=True, reminders_enabled=True)
    return SimpleNamespace(**fields)
