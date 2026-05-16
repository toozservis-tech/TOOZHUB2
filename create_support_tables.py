from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.models import Base, SupportSession, SupportMessage
SupportSession.__table__.create(bind=engine, checkfirst=True)
SupportMessage.__table__.create(bind=engine, checkfirst=True)
print("Tables created successfully.")
