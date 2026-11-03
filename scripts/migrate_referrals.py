from sqlalchemy import inspect, text
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.referrals import TABLES

def migrate_connection(connection):
    for table in TABLES: table.create(connection, checkfirst=True)
    if 'waiting_for_paid' not in {c['name'] for c in inspect(connection).get_columns('referral_rewards')}:
        connection.execute(text('ALTER TABLE referral_rewards ADD COLUMN waiting_for_paid BOOLEAN NOT NULL DEFAULT FALSE'))

def migrate(bind=None):
    with (bind or engine).begin() as connection: migrate_connection(connection)

if __name__ == '__main__': migrate()
