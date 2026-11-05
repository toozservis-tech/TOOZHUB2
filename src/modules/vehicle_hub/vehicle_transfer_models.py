"""Explicit recipient consent to a closed ownership period; never VIN-based claiming."""
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from .database import Base


class VehicleTransferInvitation(Base):
    __tablename__ = 'vehicle_transfer_invitations'
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False, index=True)
    archive_id = Column(Integer, ForeignKey('vehicle_ownership_archives.id'), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    buyer_email = Column(String(320), nullable=False, index=True)
    ownership_id = Column(Integer, ForeignKey('vehicle_ownerships.id'), nullable=False)
    ownership_started_at = Column(DateTime, nullable=False)
    released_at = Column(DateTime, nullable=False)
    status = Column(String(24), nullable=False, default='pending')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    decided_at = Column(DateTime)
    accepted_by = Column(Integer, ForeignKey('customers.id'))
    # The raw confirmation code exists only in the email and the sending process.
    code_digest = Column(String(64))
    delivery_status = Column(String(24), nullable=False, default='pending')
    delivery_attempted_at = Column(DateTime)
    sent_at = Column(DateTime)
