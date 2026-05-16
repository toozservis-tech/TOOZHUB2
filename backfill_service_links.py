import sys
import os

sys.path.insert(0, "/opt/toozhub2/app")

from src.database.session import SessionLocal
from src.modules.vehicle_hub.models import VehicleServiceLink, ServiceCustomerLink, Customer
from datetime import datetime

def run_backfill():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        links = db.query(VehicleServiceLink).filter(VehicleServiceLink.status == "approved").all()
        count = 0
        for link in links:
            service_id = link.service_customer_id
            customer_id = link.owner_customer_id
            
            existing = db.query(ServiceCustomerLink).filter(
                ServiceCustomerLink.service_customer_id == service_id,
                ServiceCustomerLink.customer_id == customer_id
            ).first()
            
            if not existing:
                service = db.query(Customer).filter(Customer.id == service_id).first()
                owner = db.query(Customer).filter(Customer.id == customer_id).first()
                if service and owner:
                    s_link = ServiceCustomerLink(
                        service_tenant_id=service.tenant_id,
                        service_customer_id=service_id,
                        customer_tenant_id=owner.tenant_id,
                        customer_id=customer_id,
                        status="active",
                        note="Propojeno přes schválení vozidla (backfill)",
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(s_link)
                    count += 1
        
        db.commit()
        print(f"Backfill complete: created {count} missing ServiceCustomerLink records.")
    finally:
        db.close()

if __name__ == "__main__":
    run_backfill()
