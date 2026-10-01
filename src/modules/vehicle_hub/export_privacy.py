"""Reviewed personal-data export fields; authentication material is never exported."""

EXPORT_FIELDS = {
    'Customer': (
        'id', 'tenant_id', 'email', 'name', 'ico', 'dic',
        'street', 'street_number', 'city', 'zip', 'phone', 'notify_email',
        'notify_sms', 'notify_stk', 'notify_oil', 'notify_general', 'role', 'reminder_settings',
        'is_disabled', 'is_deleted', 'disabled_at', 'deleted_at', 'last_login_at', 'last_seen_at',
        'created_at',
    ),
    'CustomerSecuritySettings': (
        'id', 'tenant_id', 'customer_id', 'two_factor_enabled', 'totp_enabled_at', 'biometric_enabled',
        'biometric_preferred', 'created_at', 'updated_at',
    ),
    'ServiceRegistrationRequest': (
        'id', 'status', 'email', 'ico', 'service_name', 'responsible_person',
        'phone', 'dic', 'street', 'street_number', 'city', 'zip',
        'registration_purpose', 'reviewed_by_customer_id', 'reviewed_at', 'review_note', 'approved_customer_id', 'approved_tenant_id',
        'created_at', 'updated_at',
    ),
    'ServiceCustomerLink': (
        'id', 'service_tenant_id', 'service_customer_id', 'customer_tenant_id', 'customer_id', 'status',
        'note', 'consented_at', 'consented_by_customer_id', 'created_at', 'updated_at',
    ),
    'ServiceCustomerInvite': (
        'id', 'service_tenant_id', 'service_customer_id', 'invite_email', 'invite_name', 'invite_message',
        'status', 'linked_customer_id', 'linked_customer_tenant_id', 'sent_at', 'accepted_at', 'expires_at',
        'created_at', 'updated_at',
    ),
    'ServiceDocumentIngestion': (
        'id', 'service_tenant_id', 'service_customer_id', 'customer_id', 'vehicle_id', 'source_type',
        'original_filename', 'original_mime_type', 'extracted_text', 'parsed_payload_json', 'parse_confidence', 'processing_status',
        'document_number', 'supplier_name', 'issue_date', 'due_date', 'currency', 'subtotal_without_vat',
        'vat_amount', 'total_with_vat', 'labor_total', 'materials_total', 'auto_created_service_record_id', 'created_at',
        'updated_at',
    ),
    'Vehicle': (
        'id', 'tenant_id', 'user_email', 'nickname', 'brand', 'model',
        'year', 'engine', 'vin', 'plate', 'orv_number', 'orv_scan_source',
        'orv_scanned_at', 'orv_confidence_json', 'data_trust_state', 'notes', 'stk_valid_until', 'current_mileage_km',
        'last_stk_mileage_km', 'mileage_checked_at', 'tyres_info', 'insurance_provider', 'insurance_valid_until', 'created_at',
    ),
    'ServiceRecord': (
        'id', 'tenant_id', 'vehicle_id', 'user_id', 'performed_at', 'mileage',
        'description', 'price', 'note', 'category', 'attachments', 'next_service_due_date',
        'created_by_ai', 'created_by_service_customer_id', 'service_access_link_id', 'is_deleted', 'deleted_at', 'deleted_by_user_id',
        'deletion_reason', 'snapshot_hash',
    ),
    'ServiceIntake': (
        'id', 'tenant_id', 'service_id', 'vehicle_id', 'customer_id', 'odometer_km',
        'fluids_ok', 'damage_description', 'photos', 'work_description', 'signature', 'created_at',
    ),
    'Reservation': (
        'id', 'tenant_id', 'service_id', 'customer_id', 'vehicle_id', 'service_type',
        'note', 'start_datetime', 'end_datetime', 'status', 'source_platform', 'created_at',
    ),
    'Reminder': (
        'created_by_service_customer_id',
        'id', 'tenant_id', 'customer_id', 'vehicle_id', 'type', 'text',
        'due_date', 'notify_at', 'notification_method', 'last_notified_at', 'is_manual', 'is_completed',
        'recurrence_group_id', 'recurrence_index', 'repeat_interval_days', 'created_at',
    ),
    'EmailNotificationLog': (
        'id', 'tenant_id', 'customer_id', 'email', 'subject', 'notification_type',
        'entity_id', 'sent_at', 'status',
    ),
    'PushSubscription': (
        'id', 'tenant_id', 'customer_id', 'user_agent', 'is_active', 'created_at',
        'updated_at', 'last_seen_at',
    ),
    'SecurityAccessLog': (
        'id', 'tenant_id', 'customer_id', 'user_email', 'event_type', 'ip_address',
        'country', 'region', 'city', 'latitude', 'longitude', 'timezone',
        'isp', 'source', 'user_agent', 'created_at',
    ),
    'BotCommand': (
        'id', 'tenant_id', 'user_id', 'user_email', 'user_role', 'raw_text',
        'intent_type', 'status', 'result_message', 'created_at', 'processed_at',
    ),
    'CustomerCommand': (
        'id', 'tenant_id', 'created_at', 'source', 'customer_name', 'customer_email',
        'vehicle_id', 'raw_text', 'normalized_text', 'intent_type', 'status', 'result_summary',
    ),
}

def export_fields(row):
    fields = EXPORT_FIELDS.get(type(row).__name__)
    if fields is None:
        raise ValueError("Unreviewed model cannot be exported")
    return fields
