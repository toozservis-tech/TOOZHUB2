"""Explicit pre-deploy entry point for the shared mobile API schema.

Invoked by deployment tooling only; never imported by application startup.
Each additive migration owns its transaction and is safe to retry.
"""
from scripts.migrate_service_updates import migrate as migrate_updates
from scripts.migrate_vehicle_lifecycle import migrate as migrate_lifecycle
from scripts.migrate_booking_requests import migrate as migrate_bookings
from scripts.migrate_vehicle_update_inbox import migrate as migrate_inbox
from scripts.migrate_google_billing import migrate as migrate_google
from scripts.migrate_service_job_photos import migrate as migrate_job_photos
from scripts.migrate_service_job_consent import migrate as migrate_job_consent
from scripts.migrate_service_job_workflow import migrate as migrate_job_workflow
from scripts.migrate_service_job_preregistration import migrate as migrate_job_preregistration
from scripts.migrate_home_garages import migrate as migrate_home_garages
from scripts.migrate_referrals import migrate as migrate_referrals
from scripts.migrate_vehicle_transfers import migrate as migrate_transfers
from scripts.migrate_transfer_reinvites import migrate as migrate_transfer_reinvites
from scripts.migrate_admin_incidents import migrate as migrate_admin_incidents
from scripts.migrate_admin_messages import migrate as migrate_admin_messages


def migrate(bind=None):
    migrate_updates(bind)
    migrate_lifecycle(bind)
    migrate_bookings(bind)
    migrate_inbox(bind)
    migrate_google(bind)
    migrate_job_photos(bind)
    migrate_job_consent(bind)
    migrate_job_workflow(bind)
    migrate_job_preregistration(bind)
    migrate_home_garages(bind)
    migrate_referrals(bind)
    migrate_transfers(bind)
    migrate_transfer_reinvites(bind)
    migrate_admin_incidents(bind)
    migrate_admin_messages(bind)


if __name__ == '__main__':
    migrate()
    print('Mobile release schema ready: service jobs, vehicle updates, inbox folders, owner lifecycle, booking requests, Google billing, transfer invitations and admin support cases. Existing data retained.')
