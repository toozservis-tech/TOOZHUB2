from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.apple_garages import HomeGarage

def migrate(bind=None):
    with (bind or engine).begin() as conn:
        HomeGarage.__table__.create(conn, checkfirst=True)

if __name__ == '__main__':
    migrate()
