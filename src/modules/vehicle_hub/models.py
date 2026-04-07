from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Date, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Tenant(Base):
    """Tenant (zákazník/firma) - multi-tenant architektura"""
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    license_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    instances = relationship("Instance", back_populates="tenant")


class Instance(Base):
    """Instance (konkrétní instalace aplikace na PC)"""
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    device_id = Column(String, nullable=True)
    app_version = Column(String, nullable=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="instances")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # identita / login
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)  # Hash hesla

    # fakturační / kontaktní údaje
    name = Column(String, nullable=True)          # jméno / název
    ico = Column(String, nullable=True)           # IČO (pro ARES)
    dic = Column(String, nullable=True)           # DIČ (daňové identifikační číslo)
    street = Column(String, nullable=True)        # název ulice
    street_number = Column(String, nullable=True) # číslo popisné
    city = Column(String, nullable=True)
    zip = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # kde ho kontaktovat
    notify_email = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=False)

    # co chce hlídat
    notify_stk = Column(Boolean, default=True)    # konec STK
    notify_oil = Column(Boolean, default=True)    # výměna oleje
    notify_general = Column(Boolean, default=True)  # ostatní servis

    # role uživatele
    role = Column(String, default="user", nullable=False)  # user, service, admin

    # nastavení připomínek (JSON string)
    reminder_settings = Column(Text, nullable=True)
    
    # reset hesla
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(DateTime, nullable=True)

    # Stav účtu (developer control center)
    is_disabled = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    session_version = Column(Integer, nullable=False, default=0)
    disabled_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class CustomerSecuritySettings(Base):
    """Rozšířené bezpečnostní nastavení zákazníka (2FA + biometrie preference)."""
    __tablename__ = "customer_security_settings"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True, index=True)

    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(String, nullable=True)
    totp_enabled_at = Column(DateTime, nullable=True)

    biometric_enabled = Column(Boolean, default=False, nullable=False)
    biometric_preferred = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceRegistrationRequest(Base):
    """Žádost o registraci servisního účtu čekající na schválení developerem."""
    __tablename__ = "service_registration_requests"

    id = Column(Integer, primary_key=True, index=True)

    status = Column(String, default="pending", nullable=False, index=True)  # pending, approved, rejected

    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)

    ico = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False)
    responsible_person = Column(String, nullable=False)
    phone = Column(String, nullable=False)

    dic = Column(String, nullable=True)
    street = Column(String, nullable=False)
    street_number = Column(String, nullable=True)
    city = Column(String, nullable=False)
    zip = Column(String, nullable=False)

    registration_purpose = Column(Text, nullable=False)

    reviewed_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)

    approved_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    approved_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceCustomerLink(Base):
    """Propojení servisního účtu s koncovým zákazníkem."""
    __tablename__ = "service_customer_links"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    customer_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    status = Column(String, default="active", nullable=False, index=True)  # active, archived
    note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "customer_id", name="uq_service_customer_link"),
    )


class ServiceVehicleAccess(Base):
    """Explicitní povolení přístupu servisu ke konkrétnímu vozidlu zákazníka."""
    __tablename__ = "service_vehicle_access"

    id = Column(Integer, primary_key=True, index=True)

    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    status = Column(String, default="active", nullable=False, index=True)  # active, revoked
    granted_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    note = Column(Text, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "customer_id", "vehicle_id", name="uq_service_vehicle_access"),
    )


class ServiceVehicleLookupAudit(Base):
    """Audit každého lookupu vozidla servisem přes SPZ/VIN."""
    __tablename__ = "service_vehicle_lookup_audit"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    lookup_query_raw = Column(String, nullable=True)
    lookup_query_normalized = Column(String, nullable=True, index=True)
    lookup_query_hash = Column(String, nullable=True, index=True)
    lookup_identifier_type = Column(String, nullable=False, default="unknown", index=True)  # plate, vin, unknown

    matched_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    matched_owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    result_status = Column(String, nullable=False, default="not_found", index=True)
    returned_candidate_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleServiceLink(Base):
    """Produkční source of truth pro schválený nebo odvolaný přístup servisu k vozidlu."""
    __tablename__ = "vehicle_service_links"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    source_request_id = Column(Integer, ForeignKey("service_access_requests.id"), nullable=True, index=True)
    source_type = Column(String, nullable=False, default="request_approved", index=True)
    status = Column(String, nullable=False, default="approved", index=True)  # approved, revoked

    scope_vehicle_history_read = Column(Boolean, nullable=False, default=True)
    scope_create_service_record = Column(Boolean, nullable=False, default=True)
    scope_edit_existing_records = Column(Boolean, nullable=False, default=False)
    scope_delete_existing_records = Column(Boolean, nullable=False, default=False)
    owner_data_access_level = Column(String, nullable=False, default="none")

    approved_at = Column(DateTime, nullable=True)
    approved_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    revoked_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "vehicle_id", name="uq_vehicle_service_link_pair"),
    )


class ServiceAccessRequest(Base):
    """Žádost servisu o přístup ke konkrétnímu vozidlu."""
    __tablename__ = "service_access_requests"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    lookup_audit_id = Column(Integer, ForeignKey("service_vehicle_lookup_audit.id"), nullable=True, index=True)
    requested_scope = Column(String, nullable=False, default="history_read_create_record")
    status = Column(String, nullable=False, default="pending", index=True)  # pending, approved, rejected, revoked
    request_message = Column(Text, nullable=True)

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    decision_note = Column(Text, nullable=True)
    approved_link_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceCustomerInvite(Base):
    """Pozvánka od servisu pro zákazníka (registrace / propojení účtu)."""
    __tablename__ = "service_customer_invites"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    invite_email = Column(String, nullable=False, index=True)
    invite_name = Column(String, nullable=True)
    invite_message = Column(Text, nullable=True)

    token = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, accepted, expired, cancelled

    linked_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    linked_customer_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceDocumentIngestion(Base):
    """Automatický ingest dokladů od servisu (PDF/foto/text) + strukturovaný výstup."""
    __tablename__ = "service_document_ingestions"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    source_type = Column(String, nullable=False, default="invoice", index=True)  # invoice, delivery_note, work_order, manual
    original_filename = Column(String, nullable=True)
    original_mime_type = Column(String, nullable=True)
    stored_file_path = Column(Text, nullable=True)

    extracted_text = Column(Text, nullable=True)
    parsed_payload_json = Column(Text, nullable=True)
    parse_confidence = Column(Float, nullable=True)
    processing_status = Column(String, nullable=False, default="processed", index=True)  # processed, needs_review, failed

    document_number = Column(String, nullable=True, index=True)
    supplier_name = Column(String, nullable=True)
    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    currency = Column(String, nullable=True, default="CZK")

    subtotal_without_vat = Column(Float, nullable=True)
    vat_amount = Column(Float, nullable=True)
    total_with_vat = Column(Float, nullable=True)
    labor_total = Column(Float, nullable=True)
    materials_total = Column(Float, nullable=True)

    auto_created_service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    user_email = Column(String, index=True, nullable=False)
    nickname = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    engine = Column(String, nullable=True)
    vin = Column(String, nullable=True)
    plate = Column(String, nullable=True)
    orv_number = Column(String, nullable=True, index=True)
    orv_scan_source = Column(String, nullable=True)
    orv_front_image_path = Column(Text, nullable=True)
    orv_back_image_path = Column(Text, nullable=True)
    orv_scanned_at = Column(DateTime, nullable=True)
    orv_confidence_json = Column(Text, nullable=True)
    data_trust_state = Column(String, nullable=True, index=True)
    notes = Column(String, nullable=True)
    photo_path = Column(Text, nullable=True)  # Relativní cesta k fotce vozidla uložené na serveru
    stk_valid_until = Column(Date, nullable=True)  # Datum konce platnosti STK
    current_mileage_km = Column(Integer, nullable=True)  # Aktuální stav tachometru zadaný uživatelem
    last_stk_mileage_km = Column(Integer, nullable=True)  # Poslední známý stav tachometru ze STK/emisí
    mileage_checked_at = Column(DateTime, nullable=True)  # Kdy proběhlo ověření km vůči STK
    tyres_info = Column(Text, nullable=True)  # Informace o pneumatikách
    insurance_provider = Column(String, nullable=True)  # Pojišťovna
    insurance_valid_until = Column(Date, nullable=True)  # Datum konce pojištění
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship(
        "ServiceRecord",
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )


class VehicleORVScan(Base):
    """Auditní a review vrstva pro skeny ORV před založením / úpravou vozidla."""
    __tablename__ = "vehicle_orv_scans"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    initiated_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    source = Column(String, nullable=False, default="ios_orv_scan")
    status = Column(String, nullable=False, default="processing", index=True)
    trust_state = Column(String, nullable=False, default="scanned_unverified", index=True)
    use_owner_data = Column(Boolean, nullable=False, default=False)
    front_captured = Column(Boolean, nullable=False, default=False)
    back_captured = Column(Boolean, nullable=False, default=False)

    orv_number = Column(String, nullable=True, index=True)
    front_image_path = Column(Text, nullable=True)
    back_image_path = Column(Text, nullable=True)
    front_image_hash = Column(String, nullable=True, index=True)
    back_image_hash = Column(String, nullable=True, index=True)

    front_ocr_text = Column(Text, nullable=True)
    back_ocr_text = Column(Text, nullable=True)
    parsed_vehicle_json = Column(Text, nullable=True)
    parsed_owner_json = Column(Text, nullable=True)
    confidence_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    missing_fields_json = Column(Text, nullable=True)
    extracted_fields_json = Column(Text, nullable=True)
    manual_overrides_json = Column(Text, nullable=True)

    processed_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VehicleOwnership(Base):
    """
    Explicitní vazba vlastník <-> vozidlo.
    `vehicles.user_email` zůstává jen jako kompatibilní alias pro staré klienty.
    """
    __tablename__ = "vehicle_ownerships"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    ownership_type = Column(String, nullable=False, default="owner", index=True)  # owner, delegated
    ownership_origin = Column(String, nullable=False, default="manual", index=True)
    is_primary = Column(Boolean, nullable=False, default=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    assigned_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    owned_from = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    owned_until = Column(DateTime, nullable=True, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("vehicle_id", "customer_id", "ownership_type", name="uq_vehicle_owner_assignment"),
    )


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)  # ID uživatele, který záznam vytvořil
    performed_at = Column(DateTime, default=datetime.utcnow)
    mileage = Column(Integer, nullable=True)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    note = Column(String, nullable=True)
    category = Column(String, nullable=True)  # Kategorie servisu (např. "Pravidelná údržba", "Oprava", "Výměna oleje")
    attachments = Column(Text, nullable=True)  # JSON string s přílohami
    next_service_due_date = Column(Date, nullable=True)  # Datum dalšího plánovaného servisu
    created_by_ai = Column(Boolean, default=False, nullable=False)  # True pokud byl záznam vytvořen AI asistentem
    created_by_service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_access_link_id = Column(Integer, ForeignKey("vehicle_service_links.id"), nullable=True, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    deletion_reason = Column(Text, nullable=True)
    snapshot_hash = Column(String, nullable=True, index=True)

    vehicle = relationship("Vehicle", back_populates="records")


class VehicleTachometerHistoryEntry(Base):
    """Sekundární důkazní evidence importů STK / tachometru."""
    __tablename__ = "vehicle_tachometer_history_entries"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    check_date = Column(DateTime, nullable=True, index=True)
    mileage_km = Column(Integer, nullable=True)
    protocol_number = Column(String, nullable=True, index=True)
    inspection_type = Column(String, nullable=True)
    source = Column(String, nullable=False, default="kontrolatachometru.cz")
    status = Column(String, nullable=False, default="imported", index=True)
    summary = Column(Text, nullable=True)
    findings_summary = Column(Text, nullable=True)
    findings_items_json = Column(Text, nullable=True)
    detail_snapshot_json = Column(Text, nullable=True)
    source_detail_reference = Column(Text, nullable=True)
    documents_json = Column(Text, nullable=True)  # JSON list reprezentující dostupné / nedostupné dokumenty
    raw_payload_json = Column(Text, nullable=True)  # Persistovaná metadata importovaného řádku
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "vehicle_id",
            "check_date",
            "mileage_km",
            "protocol_number",
            name="uq_vehicle_tachometer_history_entry",
        ),
    )


class ServiceRecordAuditLog(Base):
    """
    Minimální audit trail pro změny servisních záznamů.
    Uchovává snapshot před úpravou (interim řešení pro AUD-HIGH-007).
    """
    __tablename__ = "service_record_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    changed_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    action = Column(String, nullable=False, default="update")
    previous_snapshot_json = Column(Text, nullable=False)
    new_snapshot_json = Column(Text, nullable=True)
    snapshot_hash = Column(String, nullable=True, index=True)
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceIntake(Base):
    """Příjem vozidla v servisu"""
    __tablename__ = "service_intakes"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)  # ID servisu (Customer s role='service')
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    
    odometer_km = Column(Integer, nullable=True)
    fluids_ok = Column(Text, nullable=True)  # JSON string
    damage_description = Column(Text, nullable=True)
    photos = Column(Text, nullable=True)  # JSON string s listem URL
    work_description = Column(Text, nullable=True)
    signature = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Reservation(Base):
    """Rezervace v servisu"""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)  # ID servisu (Customer s role='service')
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    
    service_type = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=True)
    status = Column(String, default="PENDING", nullable=False)  # PENDING, CONFIRMED, CANCELLED
    source_platform = Column(String, nullable=True)  # ios_app / web_browser / ...
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    """Připomínky pro uživatele"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    
    type = Column(String, nullable=False)  # STK, OLEJ, SERVIS, VLASTNI, GENERAL
    text = Column(Text, nullable=False)
    due_date = Column(Date, nullable=True)
    notify_at = Column(DateTime, nullable=True)  # Přesný termín notifikace (datum + čas)
    notification_method = Column(String, nullable=True)  # app, email, both (None = dle globálního nastavení)
    last_notified_at = Column(DateTime, nullable=True)  # Kdy byla notifikace naposledy odeslána
    is_manual = Column(Boolean, default=False, nullable=False)  # True = ruční, False = automatická
    is_completed = Column(Boolean, default=False, nullable=False)
    recurrence_group_id = Column(String, nullable=True, index=True)  # Identifikátor série opakovaných připomínek
    recurrence_index = Column(Integer, nullable=False, default=0)  # Pořadí v sérii (0 = první výskyt)
    repeat_interval_days = Column(Integer, nullable=True)  # Interval opakování ve dnech pro sérii
    
    created_at = Column(DateTime, default=datetime.utcnow)


class License(Base):
    """Licence pro tenant - quota a feature flags"""
    __tablename__ = "licenses"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)
    
    plan = Column(String, nullable=False, default="free")  # "free", "basic", "premium"
    status = Column(String, nullable=False, default="active")  # "active", "inactive"
    
    vehicles_limit = Column(Integer, nullable=False, default=1)  # free=1, basic=3, premium=0 (0 = unlimited)
    
    valid_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Feature flags (volitelné, pro budoucí použití)
    vin_decode_enabled = Column(Boolean, nullable=False, default=True)
    ares_enabled = Column(Boolean, nullable=False, default=True)
    reminders_enabled = Column(Boolean, nullable=False, default=True)
    
    __table_args__ = (
        UniqueConstraint('tenant_id', name='uq_license_tenant_id'),
    )


class LicenseSubscription(Base):
    """Stav předplatného licence (Comgate recurring lifecycle)."""
    __tablename__ = "license_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)

    provider = Column(String, nullable=False, default="comgate", index=True)
    status = Column(
        String,
        nullable=False,
        default="legacy_manual",
        index=True,
    )  # active, cancel_at_period_end, grace, canceled, legacy_manual

    plan_current = Column(String, nullable=True, index=True)  # free, basic, premium
    billing_period = Column(String, nullable=True)  # monthly, yearly

    auto_renew_enabled = Column(Boolean, nullable=False, default=False)
    pending_plan_change = Column(String, nullable=True)  # free/basic/premium

    init_recurring_id = Column(String, nullable=True, index=True)

    # Kreditní saldo v haléřích:
    # kladné = kredit uživatele, záporné = nedoplatek/debt.
    credit_balance_halers = Column(Integer, nullable=False, default=0)

    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True, index=True)
    next_charge_at = Column(DateTime, nullable=True, index=True)
    grace_until = Column(DateTime, nullable=True, index=True)

    cancel_requested_at = Column(DateTime, nullable=True)
    last_payment_at = Column(DateTime, nullable=True)
    last_trans_id = Column(String, nullable=True)
    failed_renewal_attempts = Column(Integer, nullable=False, default=0)

    # Dedup notifikačních odeslání
    notified_first_payment_at = Column(DateTime, nullable=True)
    notified_renewal_failed_at = Column(DateTime, nullable=True)
    notified_grace_end_at = Column(DateTime, nullable=True)
    notified_period_d14_at = Column(DateTime, nullable=True)
    notified_period_d7_at = Column(DateTime, nullable=True)
    notified_period_d1_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_license_subscription_tenant_id"),
    )


class LicensePaymentTransaction(Base):
    """Audit + idempotence platebních událostí licencí."""
    __tablename__ = "license_payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    provider = Column(String, nullable=False, default="comgate", index=True)
    trans_id = Column(String, nullable=True, unique=True, index=True)
    ref_id = Column(String, nullable=True, index=True)

    plan = Column(String, nullable=True, index=True)
    billing_period = Column(String, nullable=True)

    amount_halers = Column(Integer, nullable=True)
    currency = Column(String, nullable=True, default="CZK")
    event_type = Column(String, nullable=False, default="unknown", index=True)
    provider_status = Column(String, nullable=True, index=True)

    payload_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EmailNotificationLog(Base):
    """Log odeslaných e-mail notifikací"""
    __tablename__ = "email_notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    notification_type = Column(String, nullable=False)  # reminder, reservation, etc.
    entity_id = Column(Integer, nullable=True)  # ID připomínky, rezervace, atd.
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, default="sent", nullable=False)  # sent, failed
    error_message = Column(Text, nullable=True)


class PushSubscription(Base):
    """Web Push subscription pro notifikace v prohlížeči."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SecurityAccessLog(Base):
    """Bezpecnostni log pristupu (login pokusy + IP/lokalita)."""
    __tablename__ = "security_access_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    user_email = Column(String, nullable=True, index=True)

    event_type = Column(String, nullable=False, index=True)  # login_success, login_failed, login_rate_limited
    endpoint = Column(String, nullable=True, index=True)

    ip_address = Column(String, nullable=True, index=True)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String, nullable=True)
    isp = Column(String, nullable=True)
    source = Column(String, nullable=True)  # source geolokace (napr. ipwho.is, private)

    user_agent = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # JSON string s doplnkovymi metadaty

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class DeveloperActionAuditLog(Base):
    """
    Immutabilní audit log vývojářských/admin akcí.
    Záznamy jsou append-only (bez API pro mazání).
    """
    __tablename__ = "developer_action_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    developer_email = Column(String, nullable=True, index=True)

    action_type = Column(String, nullable=False, index=True)
    target_resource = Column(String, nullable=False, index=True)
    parameters_json = Column(Text, nullable=True)

    result = Column(String, nullable=False, default="success", index=True)  # success, failed, blocked
    status_code = Column(Integer, nullable=True)

    request_ip = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class SecurityBlockedIp(Base):
    """Manuální blokace IP adresy pro bezpečnostní zásahy."""
    __tablename__ = "security_blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    reason = Column(Text, nullable=True)

    blocked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    blocked_by_email = Column(String, nullable=True, index=True)
    blocked_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    unblocked_at = Column(DateTime, nullable=True)
    unblocked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    unblocked_by_email = Column(String, nullable=True, index=True)


class SystemNotification(Base):
    """Systémové oznámení (broadcast) cílené na uživatele/tenant/plán."""
    __tablename__ = "system_notifications"

    id = Column(Integer, primary_key=True, index=True)

    target_type = Column(String, nullable=False, default="all", index=True)  # all | tenant | plan | user
    target_value = Column(String, nullable=True, index=True)  # tenant_id / plan / user_id

    title = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    severity = Column(String, nullable=False, default="info", index=True)  # info | warning | critical

    starts_at = Column(DateTime, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_by_email = Column(String, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VersionHistory(Base):
    """Historie verzí aplikace"""
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class VehicleTypeTemplate(Base):
    """Šablona pro typ vozidla - ukládá standardní hodnoty pro konkrétní typ vozidla"""
    __tablename__ = "vehicle_type_templates"

    id = Column(Integer, primary_key=True, index=True)
    make = Column(String, nullable=False, index=True)  # Tovární značka
    model = Column(String, nullable=False, index=True)  # Model
    engine_code = Column(String, nullable=True, index=True)  # Kód motoru
    production_year = Column(Integer, nullable=True, index=True)  # Rok výroby
    type_label = Column(String, nullable=True)  # Typ / Varianta / Verze
    
    wheels_and_tyres = Column(Text, nullable=True)  # Standardní rozměry kol a pneumatik
    extra_records = Column(Text, nullable=True)  # Dodatečné záznamy (JSON)
    default_notes = Column(Text, nullable=True)  # Výchozí poznámky
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotCommand(Base):
    """
    Model pro logování a zpracování příkazů AI asistenta
    
    ARCHITEKTURA BOTA:
    - BotCommand ukládá všechny příkazy uživatelů a jejich zpracování
    - Každý příkaz má intent_type (např. "create_task", "add_note", "create_reminder")
    - Status sleduje stav zpracování: "received" -> "processed" / "failed"
    - result_message obsahuje odpověď bota uživateli
    - error_message obsahuje chybu, pokud se něco pokazilo
    
    BEZPEČNOST:
    - Bot může provádět pouze explicitně naprogramované akce
    - Všechny akce jsou logovány v této tabulce
    - Každá akce má zjistitelný intent_type a status
    
    ROZŠÍŘENÍ:
    - V budoucnu se zde může přidat napojení na OpenAI/Claude API
    - Intent detection může být přesnější pomocí AI modelu
    - Akce mohou být rozšířeny o další typy (např. "update_vehicle", "delete_record")
    """
    __tablename__ = "bot_commands"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Identifikace uživatele a session
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)  # ID uživatele (pokud je přihlášen)
    user_email = Column(String, nullable=True, index=True)  # Email uživatele (pro případ, že není v DB)
    user_role = Column(String, nullable=True)  # Role uživatele (např. "owner", "customer", "admin")
    session_id = Column(String, nullable=True, index=True)  # Session ID pro spojení zpráv z jedné konverzace
    
    # Příkaz a jeho zpracování
    raw_text = Column(Text, nullable=False)  # Původní text příkazu od uživatele
    intent_type = Column(String, nullable=True, index=True)  # Typ záměru: "create_task", "add_note", "create_reminder", "unknown", atd.
    status = Column(String, default="received", nullable=False, index=True)  # Status: "received", "processing", "processed", "failed"
    
    # Výsledek zpracování
    result_message = Column(Text, nullable=True)  # Odpověď bota uživateli
    error_message = Column(Text, nullable=True)  # Chyba, pokud se něco pokazilo
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)  # Kdy byl příkaz zpracován
    
    # Vztah k uživateli (pokud existuje)
    customer = relationship("Customer", foreign_keys=[user_id])


class CustomerCommand(Base):
    """
    Model pro příkazy zákazníků (Command Bot v1)
    
    Tento model ukládá příkazy od zákazníků z různých zdrojů (web chat, autopilot, atd.)
    a jejich zpracování pomocí jednoduchého intent engine.
    
    ROZLIŠENÍ OD BotCommand:
    - BotCommand je pro interní AI asistenta (přihlášení uživatelé)
    - CustomerCommand je pro externí příkazy zákazníků (mohou být anonymní)
    
    V1 FUNKCIONALITA:
    - Jednoduché pravidlo-based rozpoznávání intencí (intent_type)
    - Automatické vytváření úkolů/rezervací/poznámek podle typu
    - Příprava na budoucí AI integraci (normalized_text pole)
    """
    __tablename__ = "customer_commands"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Zdroj příkazu
    source = Column(String, nullable=False, index=True)  # "web_chat", "autopilot", "internal"
    
    # Identifikace zákazníka (může být anonymní)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    
    # Text příkazu
    raw_text = Column(Text, nullable=False)  # Celý text, co zákazník napsal
    normalized_text = Column(Text, nullable=True)  # Připravené pole pro pozdější AI/normalizaci
    
    # Rozpoznání záměru
    intent_type = Column(String, nullable=False, index=True)  # "CREATE_BOOKING", "CREATE_TASK", "ADD_NOTE", "QUESTION", "UNKNOWN"
    
    # Status zpracování
    status = Column(String, default="RECEIVED", nullable=False, index=True)  # "RECEIVED", "EXECUTED", "FAILED"
    
    # Výsledek zpracování
    result_summary = Column(Text, nullable=True)  # Stručně, co se stalo – "vytvořen úkol #123"
    error_message = Column(Text, nullable=True)  # Chybová zpráva, pokud se něco pokazilo
    
    # Vztahy
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])
