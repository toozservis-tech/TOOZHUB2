"""Immutable owner decisions. An owner's report is not a registry declaration."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text, UniqueConstraint, event
from sqlalchemy.orm import Session
from .database import Base


class VehicleLifecycleEvent(Base):
    __tablename__ = 'vehicle_lifecycle_events'
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False, index=True)
    ownership_id = Column(Integer, ForeignKey('vehicle_ownerships.id'), nullable=False, index=True)
    ownership_started_at = Column(DateTime, nullable=False)
    owner_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    client_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    action = Column(String(24), nullable=False)
    state = Column(String(24), nullable=False)
    version = Column(Integer, nullable=False)
    note = Column(Text, nullable=True)
    effective_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    archive_id = Column(Integer, ForeignKey('vehicle_ownership_archives.id'), nullable=True)
    response_json = Column(Text, nullable=False)
    __table_args__ = (
        UniqueConstraint('actor_id', 'client_id', name='uq_vehicle_lifecycle_client'),
        UniqueConstraint('ownership_id', 'ownership_started_at', 'version', name='uq_vehicle_lifecycle_version'),
    )


@event.listens_for(Session, 'before_flush')
def guard_lifecycle_events(db, context, instances):
    for row in list(db.dirty) + list(db.deleted):
        if isinstance(row, VehicleLifecycleEvent) and (row in db.deleted or db.is_modified(row)):
            raise RuntimeError('Vehicle lifecycle events are immutable')
