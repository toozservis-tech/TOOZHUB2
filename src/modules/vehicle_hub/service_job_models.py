"""Append-only workshop job timeline, separate from private ownership history."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint, Float
from .database import Base


class ServiceJob(Base):
    __tablename__ = 'service_jobs'
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id'), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey('vehicles.id'), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey('customers.id'), nullable=False, index=True)
    intake_id = Column(Integer, ForeignKey('service_intakes.id'), nullable=True, unique=True)
    ownership_started_at = Column(DateTime, nullable=False)
    ownership_id = Column(Integer, ForeignKey('vehicle_ownerships.id'), nullable=False, index=True)
    vin_snapshot = Column(String, nullable=True)
    client_id = Column(String(36), nullable=False)
    creation_hash = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default='received')
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    mileage = Column(Integer, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    final_record_id = Column(Integer, ForeignKey('service_records.id'), nullable=True, unique=True)
    access_request_id = Column(Integer, ForeignKey('service_access_requests.id'), nullable=True, index=True)
    consent_published_at = Column(DateTime, nullable=True)
    completion_price = Column(Float, nullable=True)
    workflow_version = Column(Integer, nullable=False, default=0, server_default='0')
    __table_args__ = (UniqueConstraint('service_id', 'client_id', name='uq_service_job_client'),)


class ServiceJobEvent(Base):
    __tablename__ = 'service_job_events'
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('service_jobs.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    client_id = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('job_id', 'client_id', name='uq_service_job_event_client'),)


class ServiceJobPhoto(Base):
    """Immutable, owner-period-bound image reference for service-job evidence."""
    __tablename__ = 'service_job_photos'
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('service_jobs.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    client_id = Column(String(36), nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(500), nullable=False)
    mime_type = Column(String(64), nullable=False)
    file_size = Column(Integer, nullable=False)
    caption = Column(String(200), nullable=True)
    stage = Column(String(32), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('job_id', 'client_id', name='uq_service_job_photo_client'),)


class ServiceJobDocument(Base):
    """Original PDF evidence, private to the workshop until owner consent."""
    __tablename__ = 'service_job_documents'
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('service_jobs.id'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('customers.id'), nullable=False)
    client_id = Column(String(36), nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(64), nullable=False, default='application/pdf')
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('job_id', 'client_id', name='uq_service_job_document_client'),)
