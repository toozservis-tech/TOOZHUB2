"""Service enquiries remain separate from confirmed calendar reservations."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from .database import Base


class BookingRequest(Base):
    __tablename__ = 'service_booking_requests'
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False, index=True)
    ownership_id = Column(Integer, ForeignKey('vehicle_ownerships.id'), nullable=False)
    ownership_started_at = Column(DateTime, nullable=False)
    vehicle_name = Column(String(200), nullable=False)
    vehicle_plate = Column(String(64))
    client_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    service_type = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    preferred_datetime = Column(DateTime)
    proposed_datetime = Column(DateTime)
    service_reply = Column(Text)
    status = Column(String(24), nullable=False, default='pending')
    version = Column(Integer, nullable=False, default=1)
    reservation_id = Column(Integer, ForeignKey('reservations.id'), unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('owner_id', 'client_id', name='uq_booking_request_client'),)


class BookingRequestEvent(Base):
    __tablename__ = 'service_booking_request_events'
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey('service_booking_requests.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    client_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    action = Column(String(24), nullable=False)
    message = Column(Text)
    proposed_datetime = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('request_id', 'client_id', name='uq_booking_request_event_client'),)
