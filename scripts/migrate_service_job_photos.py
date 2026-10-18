"""Pre-deploy creation of job photo evidence table, never run on requests."""
from sqlalchemy import inspect
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.service_job_models import ServiceJobPhoto


def migrate(bind=None):
    target = bind or engine
    with target.begin() as conn:
        if inspect(conn).has_table(ServiceJobPhoto.__tablename__):
            return
        ServiceJobPhoto.__table__.create(conn, checkfirst=True)


if __name__ == "__main__":
    migrate()
    print("Service job photo evidence schema ready.")
