"""Google Play ownership is immutable; account deletion leaves an anonymous tombstone."""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from src.modules.vehicle_hub.database import Base


class GoogleBillingIdentity(Base):
    __tablename__ = "google_billing_identities"
    token = Column(String(64), primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), unique=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class GoogleSubscription(Base):
    __tablename__ = "google_subscriptions"
    # SHA256 of package + purchase token. Tokens are not order IDs and are never logged.
    id = Column(String(64), primary_key=True)
    account_token = Column(String(64), ForeignKey("google_billing_identities.token"), nullable=False, index=True)
    encrypted_token = Column(Text, nullable=False)
    package_name = Column(String, nullable=False)
    test_purchase = Column(Boolean, nullable=False, default=False)
    product_id = Column(String, nullable=False)
    base_plan_id = Column(String, nullable=False)
    plan = Column(String, nullable=False)
    period = Column(String, nullable=False)
    state = Column(String, nullable=False)
    expires_at = Column(DateTime)
    auto_renew = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=False)
    acknowledged = Column(Boolean, nullable=False, default=False)
    linked_id = Column(String(64))
    superseded_by = Column(String(64), index=True)
    verified_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    next_check_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    claim_token = Column(String(36))
    failures = Column(Integer, nullable=False, default=0)
    last_result = Column(String, nullable=False, default="verified")
