"""Additive migration only. Does not modify existing accounts, licenses or Comgate."""
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub import models  # Register referenced customer/tenant tables.
from src.modules.licensing.apple_models import AppleBillingIdentity, AppleSubscription, AppleReconciliationState


def migrate(bind=engine):
    with bind.begin() as connection:
        AppleBillingIdentity.__table__.create(connection, checkfirst=True)
        AppleSubscription.__table__.create(connection, checkfirst=True)
        AppleReconciliationState.__table__.create(connection, checkfirst=True)


if __name__ == "__main__":
    migrate()
    print("Apple billing tables are ready; existing data retained.")
