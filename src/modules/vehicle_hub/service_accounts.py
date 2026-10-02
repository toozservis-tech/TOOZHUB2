"""A service recipient is a service account, never an administrator."""
from sqlalchemy import func

from src.core.rbac import is_service
from .models import Customer


def active_service_filters():
    """Shared SQL predicate for selectable services and booking recipients."""
    return (
        func.lower(func.trim(Customer.role)) == "service",
        Customer.is_disabled.is_(False),
        Customer.is_deleted.is_(False),
    )


def is_active_service_account(customer: Customer | None) -> bool:
    return bool(customer and is_service(customer.role)
                and not customer.is_disabled and not customer.is_deleted)
