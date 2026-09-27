"""Private, append-only repair visit photo documentation."""
from alembic import op
from src.modules.vehicle_hub.models import RepairPhotoSession, RepairEvidencePhoto
revision = "20260927_0010"
down_revision = "20260927_0009"
branch_labels = None
depends_on = None

def upgrade():
    RepairPhotoSession.__table__.create(op.get_bind(), checkfirst=True)
    RepairEvidencePhoto.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    raise RuntimeError("Photo evidence requires a reviewed, non-destructive rollback.")
