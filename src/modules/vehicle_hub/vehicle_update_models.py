"""Durable owner inbox. Event content is immutable; read state is separate."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Boolean, CheckConstraint
from .database import Base


class VehicleUpdate(Base):
    __tablename__ = "vehicle_updates"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    ownership_id = Column(Integer, ForeignKey("vehicle_ownerships.id"), nullable=False)
    ownership_started_at = Column(DateTime, nullable=False)
    actor_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    service_job_id = Column(Integer, nullable=True)
    event_type = Column(String(100), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    source_type = Column(String(80), nullable=False)
    source_id = Column(Integer, nullable=False)
    dedupe_key = Column(String(240), nullable=False, unique=True)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("ix_vehicle_updates_inbox", "recipient_id", "id"),)


class VehicleUpdateReceipt(Base):
    __tablename__ = "vehicle_update_receipts"
    update_id = Column(Integer, ForeignKey("vehicle_updates.id"), primary_key=True)
    recipient_id = Column(Integer, ForeignKey("customers.id"), primary_key=True)
    read_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class VehicleUpdateInboxState(Base):
    """Recipient-only presentation state; no row means the original inbox."""
    __tablename__ = "vehicle_update_inbox_states"
    update_id = Column(Integer, ForeignKey("vehicle_updates.id"), primary_key=True)
    recipient_id = Column(Integer, ForeignKey("customers.id"), primary_key=True)
    folder = Column(String(16), nullable=False, default="inbox")
    archived_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        CheckConstraint("folder IN ('inbox', 'archive', 'trash')", name="ck_vehicle_update_inbox_folder"),
        Index("ix_vehicle_update_inbox_recipient_folder", "recipient_id", "folder", "update_id"),
    )


class VehicleUpdateInboxAction(Base):
    """Append-only history of actual recipient changes, including unread/reset."""
    __tablename__ = "vehicle_update_inbox_actions"
    id = Column(Integer, primary_key=True)
    update_id = Column(Integer, ForeignKey("vehicle_updates.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    from_read = Column(Boolean, nullable=False)
    to_read = Column(Boolean, nullable=False)
    from_folder = Column(String(16), nullable=False)
    to_folder = Column(String(16), nullable=False)
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (Index("ix_vehicle_update_inbox_action_recipient", "recipient_id", "update_id", "id"),)
