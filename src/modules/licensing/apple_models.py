"""Apple billing identity and verified subscription snapshots, separate from Comgate."""
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from src.modules.vehicle_hub.database import Base


class AppleBillingIdentity(Base):
    __tablename__ = "apple_billing_identities"
    token = Column(String(36), primary_key=True)
    # Keep an anonymous tombstone after deletion: a purchase must not move to a new account.
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), unique=True, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AppleSubscription(Base):
    __tablename__ = "apple_subscriptions"
    # Environment + original transaction ID. Never mix sandbox and real purchases.
    id = Column(String, primary_key=True)
    account_token = Column(String(36), ForeignKey("apple_billing_identities.token"), nullable=False, index=True)
    environment = Column(String, nullable=False)
    original_transaction_id = Column(String, nullable=False)
    transaction_id = Column(String, nullable=False)
    product_id = Column(String, nullable=False)
    plan = Column(String, nullable=False)
    period = Column(String, nullable=False)
    status = Column(Integer, nullable=False)
    signed_date = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    access_until = Column(DateTime, nullable=False)
    auto_renew = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AppleReconciliationState(Base):
    """Durable schedule and short lease; contains no Apple credentials or JWS."""
    __tablename__ = "apple_reconciliation_state"
    subscription_id = Column(String, ForeignKey("apple_subscriptions.id", ondelete="CASCADE"), primary_key=True)
    next_check_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    claim_token = Column(String(36), nullable=True)
    last_attempt_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_result = Column(String, nullable=True)
    failures = Column(Integer, nullable=False, default=0)
