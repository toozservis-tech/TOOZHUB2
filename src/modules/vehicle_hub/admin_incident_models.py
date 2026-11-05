"""Additive admin support cases. Original security events remain immutable."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from .database import Base


class AdminIncident(Base):
    __tablename__ = 'admin_incidents'
    id = Column(Integer, primary_key=True)
    source_event_id = Column(Integer, ForeignKey('security_access_logs.id'), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), index=True)
    actor_key = Column(String(400), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    # NULL for closed cases: recurrence can form a NEW case without erasing closure.
    active_fingerprint = Column(String(64), unique=True)
    status = Column(String(24), nullable=False, default='open', index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_by = Column(Integer, ForeignKey('customers.id'), nullable=True)
    __table_args__ = (CheckConstraint("status IN ('open','in_progress','resolved','dismissed')", name='ck_admin_incident_status'),)


class AdminIncidentEvent(Base):
    __tablename__ = 'admin_incident_events'
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey('admin_incidents.id'), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey('security_access_logs.id'), nullable=False, unique=True)
    linked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AdminIncidentHistory(Base):
    __tablename__ = 'admin_incident_history'
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey('admin_incidents.id'), nullable=False, index=True)
    admin_id = Column(Integer, ForeignKey('customers.id'), nullable=True)
    action = Column(String(32), nullable=False)
    status = Column(String(24), nullable=False)
    note = Column(Text, nullable=False, default='')
    client_id = Column(String(36))
    request_hash = Column(String(64))
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('incident_id','admin_id','client_id', name='uq_admin_incident_command'),)


TABLES = [AdminIncident.__table__, AdminIncidentEvent.__table__, AdminIncidentHistory.__table__]


def erase_account_diagnostics(db, customer):
    """Explicit account erasure is the sole exception to append-only support history.

    Follow the existing erasure scope of SecurityAccessLog; never leave identity
    or arbitrary private notes behind, and never block erasure via new FKs.
    """
    from sqlalchemy import inspect, or_, func
    from .models import SecurityAccessLog
    if not all(inspect(db.connection()).has_table(table.name) for table in TABLES):return
    email=(customer.email or '').strip().lower()
    event_ids=db.query(SecurityAccessLog.id).filter(or_(SecurityAccessLog.customer_id==customer.id,func.lower(SecurityAccessLog.user_email)==email))
    linked=db.query(AdminIncidentEvent.incident_id).filter(AdminIncidentEvent.event_id.in_(event_ids))
    case_ids=[identity for (identity,) in db.query(AdminIncident.id).filter(or_(
        AdminIncident.customer_id==customer.id,func.lower(AdminIncident.actor_key)==email,AdminIncident.id.in_(linked)))]
    if case_ids:
        db.query(AdminIncidentHistory).filter(AdminIncidentHistory.incident_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(AdminIncidentEvent).filter(AdminIncidentEvent.incident_id.in_(case_ids)).delete(synchronize_session=False)
        db.query(AdminIncident).filter(AdminIncident.id.in_(case_ids)).delete(synchronize_session=False)
    db.query(AdminIncident).filter_by(created_by=customer.id).update({'created_by':None},synchronize_session=False)
    db.query(AdminIncidentHistory).filter_by(admin_id=customer.id).update({
        'admin_id':None,'note':'Obsah poznámky odstraněn při výmazu autora účtu.',
        'client_id':None,'request_hash':None},synchronize_session=False)
