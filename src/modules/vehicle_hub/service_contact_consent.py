"""Serialize invitation decisions; a legacy address-book link grants no access."""
from fastapi import HTTPException
from sqlalchemy import inspect, text, update

from .models import Customer, ServiceCustomerLink


def migrate_contact_consent(connection):
    """Add nullable proof fields without rewriting historical relationships."""
    existing = {c['name'] for c in inspect(connection).get_columns('service_customer_links')}
    for name, sql_type in [('consented_at', 'TIMESTAMP'), ('consented_by_customer_id', 'INTEGER')]:
        if name not in existing:
            connection.execute(text(f'ALTER TABLE service_customer_links ADD COLUMN {name} {sql_type} NULL'))
    if 'reminders' in inspect(connection).get_table_names():
        columns = {c['name'] for c in inspect(connection).get_columns('reminders')}
        if 'created_by_service_customer_id' not in columns:
            connection.execute(text('ALTER TABLE reminders ADD COLUMN created_by_service_customer_id INTEGER NULL'))


def lock_service_contacts(db, service_id):
    # Serialize send/resend/accept/disconnect for a service. No network operations
    # occur before releasing this transaction lock. Keep this lock before any
    # vehicle locks when an operation also revokes vehicle access.
    if db.get_bind().dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(:namespace, :service)'),
            {'namespace': 1398162255, 'service': int(service_id)})
    elif db.get_bind().dialect.name == 'sqlite':
        db.execute(update(Customer).where(Customer.id == service_id).values(id=Customer.id))
    else:
        raise HTTPException(503, 'Propojení nyní nelze bezpečně ověřit.')


def has_contact_consent(link: ServiceCustomerLink | None, customer_id: int) -> bool:
    return bool(link and link.status == 'active' and link.consented_at
        and link.consented_by_customer_id == customer_id)
