"""Complete schema required by existing application modules.

Additive migration; existing data and permissions are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0008"
down_revision = "20260406_0007"
branch_labels = None
depends_on = None

def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if 'vehicle_type_templates' not in existing:
        op.create_table('vehicle_type_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('make', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('engine_code', sa.String(), nullable=True),
        sa.Column('production_year', sa.Integer(), nullable=True),
        sa.Column('type_label', sa.String(), nullable=True),
        sa.Column('wheels_and_tyres', sa.Text(), nullable=True),
        sa.Column('extra_records', sa.Text(), nullable=True),
        sa.Column('default_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_vehicle_type_templates_engine_code'), 'vehicle_type_templates', ['engine_code'], unique=False)
        op.create_index(op.f('ix_vehicle_type_templates_id'), 'vehicle_type_templates', ['id'], unique=False)
        op.create_index(op.f('ix_vehicle_type_templates_make'), 'vehicle_type_templates', ['make'], unique=False)
        op.create_index(op.f('ix_vehicle_type_templates_model'), 'vehicle_type_templates', ['model'], unique=False)
        op.create_index(op.f('ix_vehicle_type_templates_production_year'), 'vehicle_type_templates', ['production_year'], unique=False)
    if 'bot_commands' not in existing:
        op.create_table('bot_commands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_email', sa.String(), nullable=True),
        sa.Column('user_role', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('intent_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('result_message', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['customers.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_bot_commands_created_at'), 'bot_commands', ['created_at'], unique=False)
        op.create_index(op.f('ix_bot_commands_id'), 'bot_commands', ['id'], unique=False)
        op.create_index(op.f('ix_bot_commands_intent_type'), 'bot_commands', ['intent_type'], unique=False)
        op.create_index(op.f('ix_bot_commands_session_id'), 'bot_commands', ['session_id'], unique=False)
        op.create_index(op.f('ix_bot_commands_status'), 'bot_commands', ['status'], unique=False)
        op.create_index(op.f('ix_bot_commands_tenant_id'), 'bot_commands', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_bot_commands_user_email'), 'bot_commands', ['user_email'], unique=False)
        op.create_index(op.f('ix_bot_commands_user_id'), 'bot_commands', ['user_id'], unique=False)
    if 'customer_commands' not in existing:
        op.create_table('customer_commands',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('customer_name', sa.String(), nullable=True),
        sa.Column('customer_email', sa.String(), nullable=True),
        sa.Column('vehicle_id', sa.Integer(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('normalized_text', sa.Text(), nullable=True),
        sa.Column('intent_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_customer_commands_created_at'), 'customer_commands', ['created_at'], unique=False)
        op.create_index(op.f('ix_customer_commands_customer_email'), 'customer_commands', ['customer_email'], unique=False)
        op.create_index(op.f('ix_customer_commands_id'), 'customer_commands', ['id'], unique=False)
        op.create_index(op.f('ix_customer_commands_intent_type'), 'customer_commands', ['intent_type'], unique=False)
        op.create_index(op.f('ix_customer_commands_source'), 'customer_commands', ['source'], unique=False)
        op.create_index(op.f('ix_customer_commands_status'), 'customer_commands', ['status'], unique=False)
        op.create_index(op.f('ix_customer_commands_tenant_id'), 'customer_commands', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_customer_commands_vehicle_id'), 'customer_commands', ['vehicle_id'], unique=False)
    if 'email_notification_logs' not in existing:
        op.create_table('email_notification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('notification_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_email_notification_logs_customer_id'), 'email_notification_logs', ['customer_id'], unique=False)
        op.create_index(op.f('ix_email_notification_logs_email'), 'email_notification_logs', ['email'], unique=False)
        op.create_index(op.f('ix_email_notification_logs_id'), 'email_notification_logs', ['id'], unique=False)
        op.create_index(op.f('ix_email_notification_logs_tenant_id'), 'email_notification_logs', ['tenant_id'], unique=False)
    if 'service_intakes' not in existing:
        op.create_table('service_intakes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('service_id', sa.Integer(), nullable=False),
        sa.Column('vehicle_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('odometer_km', sa.Integer(), nullable=True),
        sa.Column('fluids_ok', sa.Text(), nullable=True),
        sa.Column('damage_description', sa.Text(), nullable=True),
        sa.Column('photos', sa.Text(), nullable=True),
        sa.Column('work_description', sa.Text(), nullable=True),
        sa.Column('signature', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['service_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_service_intakes_customer_id'), 'service_intakes', ['customer_id'], unique=False)
        op.create_index(op.f('ix_service_intakes_id'), 'service_intakes', ['id'], unique=False)
        op.create_index(op.f('ix_service_intakes_service_id'), 'service_intakes', ['service_id'], unique=False)
        op.create_index(op.f('ix_service_intakes_tenant_id'), 'service_intakes', ['tenant_id'], unique=False)
        op.create_index(op.f('ix_service_intakes_vehicle_id'), 'service_intakes', ['vehicle_id'], unique=False)
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("licenses")}
    for name in ("vin_decode_enabled", "ares_enabled", "reminders_enabled"):
        if name not in columns:
            op.add_column("licenses", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true()))

def downgrade():
    raise RuntimeError("This additive migration requires a reviewed manual rollback; no data is deleted automatically.")
