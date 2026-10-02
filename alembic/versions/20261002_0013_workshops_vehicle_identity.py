"""Workshop locations, reversible merge markers and SQL-level VIN reservation."""
from alembic import op
import sqlalchemy as sa

revision = '20261002_0013'
down_revision = '20261001_0012'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ('customers', 'service_registration_requests'):
        existing = {c['name'] for c in sa.inspect(bind).get_columns(name)}
        for field, kind in [('workshop_same_as_registered', sa.Boolean()), ('workshop_street', sa.String()),
                            ('workshop_street_number', sa.String()), ('workshop_city', sa.String()), ('workshop_zip', sa.String())]:
            if field not in existing:
                op.add_column(name, sa.Column(field, kind, nullable=True))
    existing = {c['name'] for c in sa.inspect(bind).get_columns('vehicles')}
    if 'merged_into_id' not in existing:
        op.add_column('vehicles', sa.Column('merged_into_id', sa.Integer(), nullable=True))
        op.create_index('ix_vehicles_merged_into_id', 'vehicles', ['merged_into_id'])
    if 'merged_vin' not in existing:
        op.add_column('vehicles', sa.Column('merged_vin', sa.String(), nullable=True))
    if 'vehicle_vin_claims' not in sa.inspect(bind).get_table_names():
        op.create_table('vehicle_vin_claims', sa.Column('vin', sa.String(), primary_key=True),
                        sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id', ondelete='CASCADE'), nullable=False))
        op.create_index('ix_vehicle_vin_claims_vehicle_id', 'vehicle_vin_claims', ['vehicle_id'])
    if bind.dialect.name == 'postgresql':
        if not any(fk['constrained_columns'] == ['merged_into_id'] for fk in sa.inspect(bind).get_foreign_keys('vehicles')):
            op.create_foreign_key('fk_vehicle_merge_target', 'vehicles', 'vehicles', ['merged_into_id'], ['id'])
        # Existing duplicates remain untouched for an administrator to review.
        # Every future writer must reserve the normalized VIN in a unique table.
        op.execute("""INSERT INTO vehicle_vin_claims(vin, vehicle_id)
            SELECT regexp_replace(upper(vin), '[^A-Z0-9]', '', 'g'), min(id) FROM vehicles
            WHERE vin IS NOT NULL AND merged_into_id IS NULL
              AND regexp_replace(upper(vin), '[^A-Z0-9]', '', 'g') <> ''
            GROUP BY regexp_replace(upper(vin), '[^A-Z0-9]', '', 'g') ON CONFLICT DO NOTHING""")
        op.execute("""CREATE OR REPLACE FUNCTION sv_guard_vehicle_vin() RETURNS trigger AS $$
        DECLARE key text; plate_key text; claimed integer; changed_identity boolean;
        BEGIN
          key := regexp_replace(upper(COALESCE(NEW.vin, '')), '[^A-Z0-9]', '', 'g');
          plate_key := regexp_replace(upper(COALESCE(NEW.plate, '')), '[^A-Z0-9]', '', 'g');
          changed_identity := TG_OP = 'INSERT';
          IF TG_OP = 'UPDATE' THEN
            changed_identity := regexp_replace(upper(COALESCE(OLD.vin, '')), '[^A-Z0-9]', '', 'g') <> key
              OR regexp_replace(upper(COALESCE(OLD.plate, '')), '[^A-Z0-9]', '', 'g') <> plate_key;
          END IF;
          IF NEW.merged_into_id IS NULL AND plate_key <> '' AND changed_identity THEN
            PERFORM pg_advisory_xact_lock(hashtextextended('sv:plate:' || plate_key, 0));
            IF EXISTS(SELECT 1 FROM vehicles WHERE id <> NEW.id AND merged_into_id IS NULL
              AND regexp_replace(upper(COALESCE(plate, '')), '[^A-Z0-9]', '', 'g') = plate_key
              AND (key = '' OR regexp_replace(upper(COALESCE(vin, '')), '[^A-Z0-9]', '', 'g') = '')) THEN
              RAISE unique_violation USING MESSAGE = 'Vozidlo s touto SPZ již existuje. Ověřte VIN.', CONSTRAINT = 'uq_vehicle_unidentified_plate';
            END IF;
          END IF;
          IF TG_OP = 'UPDATE' THEN
            DELETE FROM vehicle_vin_claims WHERE vehicle_id = OLD.id AND vin <> key;
          END IF;
          IF key <> '' AND NEW.merged_into_id IS NULL THEN
            INSERT INTO vehicle_vin_claims(vin, vehicle_id) VALUES(key, NEW.id)
              ON CONFLICT(vin) DO UPDATE SET vin = EXCLUDED.vin RETURNING vehicle_id INTO claimed;
            IF claimed <> NEW.id THEN
              RAISE unique_violation USING MESSAGE = 'Vozidlo s tímto VIN již existuje.', CONSTRAINT = 'uq_vehicle_normalized_vin';
            END IF;
            IF TG_OP = 'INSERT' OR regexp_replace(upper(COALESCE(OLD.vin, '')), '[^A-Z0-9]', '', 'g') <> key THEN
              IF EXISTS(SELECT 1 FROM vehicles WHERE id <> NEW.id AND merged_into_id IS NULL
                AND regexp_replace(upper(COALESCE(vin, '')), '[^A-Z0-9]', '', 'g') = key) THEN
                RAISE unique_violation USING MESSAGE = 'Vozidlo s tímto VIN již existuje.', CONSTRAINT = 'uq_vehicle_normalized_vin';
              END IF;
            END IF;
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute('DROP TRIGGER IF EXISTS sv_vehicle_vin_guard ON vehicles')
        # Unrelated updates to a legacy duplicate must remain possible.
        op.execute('CREATE TRIGGER sv_vehicle_vin_guard AFTER INSERT OR UPDATE OF vin, plate, merged_into_id ON vehicles FOR EACH ROW EXECUTE FUNCTION sv_guard_vehicle_vin()')


def downgrade():
    raise RuntimeError('Workshop and merge history require a reviewed non-destructive rollback.')
