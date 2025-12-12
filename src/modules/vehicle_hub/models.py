from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Date, Text
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
    
    created_at = Column(DateTime, default=datetime.utcnow)


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
    notes = Column(String, nullable=True)
    stk_valid_until = Column(Date, nullable=True)  # Datum konce platnosti STK
    tyres_info = Column(Text, nullable=True)  # Informace o pneumatikách
    insurance_provider = Column(String, nullable=True)  # Pojišťovna
    insurance_valid_until = Column(Date, nullable=True)  # Datum konce pojištění
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship(
        "ServiceRecord",
        back_populates="vehicle",
        cascade="all, delete-orphan",
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

    vehicle = relationship("Vehicle", back_populates="records")


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
    is_manual = Column(Boolean, default=False, nullable=False)  # True = ruční, False = automatická
    is_completed = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)


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

