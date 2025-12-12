"""
Pydantic schémata pro API v1.0
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime, date


# ==========================
#   VOZIDLA
# ==========================

class VehicleCreateV1(BaseModel):
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: Optional[date] = None
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    # assigned_service_id: Optional[int] = None  # ID servisu přiřazeného k vozidlu - DOČASNĚ ZAKÁZÁNO


class VehicleUpdateV1(BaseModel):
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: Optional[date] = None
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    # assigned_service_id: Optional[int] = None  # ID servisu přiřazeného k vozidlu - DOČASNĚ ZAKÁZÁNO


class VehicleOutV1(BaseModel):
    id: int
    user_email: str
    nickname: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    engine: Optional[str]
    vin: Optional[str]
    plate: Optional[str]
    notes: Optional[str]
    stk_valid_until: Optional[date]
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    # assigned_service_id: Optional[int] = None  # DOČASNĚ ZAKÁZÁNO
    tenant_id: Optional[int] = None  # Multi-tenant podpora
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==========================
#   SERVISNÍ ZÁZNAMY
# ==========================

class ServiceRecordCreateV1(BaseModel):
    performed_at: Optional[datetime] = None  # Může být None
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    note: Optional[str] = None
    category: Optional[str] = None  # OLEJ, BRZDY, PNEU, STK, DIAGNOSTIKA, ...
    attachments: Optional[str] = None  # JSON string nebo text
    next_service_due_date: Optional[date] = None


class ServiceRecordUpdateV1(BaseModel):
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = None
    description: Optional[str] = None
    price: Optional[float] = None
    note: Optional[str] = None
    category: Optional[str] = None
    attachments: Optional[str] = None
    next_service_due_date: Optional[date] = None


class ServiceRecordOutV1(BaseModel):
    id: int
    vehicle_id: int
    user_id: Optional[int]
    performed_at: Optional[datetime]  # Může být None
    mileage: Optional[int]
    description: str
    price: Optional[float]
    note: Optional[str]
    category: Optional[str]
    attachments: Optional[str]
    next_service_due_date: Optional[date]
    created_by_ai: bool = False  # True pokud byl záznam vytvořen AI asistentem
    
    class Config:
        from_attributes = True


# ==========================
#   SERVISNÍ PŘÍJEM (INTAKE)
# ==========================

class ServiceIntakeCreateV1(BaseModel):
    vehicle_id: int
    customer_id: int
    odometer_km: Optional[int] = None
    fluids_ok: Optional[str] = None  # JSON string
    damage_description: Optional[str] = None
    photos: Optional[str] = None  # JSON string s listem URL
    work_description: Optional[str] = None
    signature: Optional[str] = None


class ServiceIntakeOutV1(BaseModel):
    id: int
    service_id: int
    vehicle_id: int
    customer_id: int
    odometer_km: Optional[int]
    fluids_ok: Optional[str]
    damage_description: Optional[str]
    photos: Optional[str]
    work_description: Optional[str]
    signature: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==========================
#   REZERVACE
# ==========================

class ReservationCreateV1(BaseModel):
    service_id: int
    vehicle_id: int
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: datetime
    end_datetime: Optional[datetime] = None


class ReservationUpdateV1(BaseModel):
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    status: Optional[str] = None  # PENDING, CONFIRMED, CANCELLED


class ReservationOutV1(BaseModel):
    id: int
    service_id: int
    customer_id: int
    vehicle_id: int
    service_type: Optional[str]
    note: Optional[str]
    start_datetime: datetime
    end_datetime: Optional[datetime]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==========================
#   PŘIPOMÍNKY
# ==========================

class ReminderOutV1(BaseModel):
    id: Optional[int] = None  # ID pro ruční připomínky
    type: str  # STK, OLEJ, SERVIS, VLASTNI, GENERAL
    vehicle_id: Optional[int] = None
    vehicle_name: Optional[str] = None
    text: str
    due_date: Optional[date] = None
    is_manual: bool = False  # True = ruční, False = automatická
    is_completed: Optional[bool] = False


class ReminderCreateV1(BaseModel):
    """Model pro vytvoření ruční připomínky"""
    vehicle_id: Optional[int] = None
    type: str  # STK, OLEJ, SERVIS, VLASTNI
    text: str
    due_date: Optional[date] = None


class ReminderUpdateV1(BaseModel):
    """Model pro aktualizaci připomínky"""
    type: Optional[str] = None  # Typ připomínky (STK, OLEJ, SERVIS, VLASTNI)
    vehicle_id: Optional[int] = None  # ID vozidla (nebo None pro obecnou)
    text: Optional[str] = None
    due_date: Optional[date] = None
    is_completed: Optional[bool] = None


# ==========================
#   NASTAVENÍ PŘIPOMÍNEK
# ==========================

class STKReminderSettings(BaseModel):
    enabled: bool = True
    days_before: int = 30  # Kolik dní před koncem STK připomínat

class OilReminderSettings(BaseModel):
    enabled: bool = True
    km_interval: int = 15000  # Interval v km
    km_warning: int = 5000  # Varování X km před
    days_interval: int = 365  # Interval ve dnech
    days_warning: int = 30  # Varování X dní před

class ServiceCategorySettings(BaseModel):
    enabled: bool = True
    km_interval: Optional[int] = None
    days_interval: Optional[int] = None

class GeneralReminderSettings(BaseModel):
    enabled: bool = True
    days_before: int = 30  # Kolik dní před plánovaným servisem

class NotificationSettings(BaseModel):
    """Globální nastavení upozornění pro připomínky"""
    notification_method: str = "app"  # "app" = pouze v aplikaci, "email" = e-mail, "both" = obojí
    notify_days_before: int = 7  # Počet dní předem upozornit

class ReminderSettingsV1(BaseModel):
    enabled: bool = True
    stk: Optional[STKReminderSettings] = None
    oil: Optional[OilReminderSettings] = None
    service_categories: Optional[Dict[str, ServiceCategorySettings]] = None
    general: Optional[GeneralReminderSettings] = None
    notification: Optional[NotificationSettings] = None  # Globální nastavení upozornění

class ReminderSettingsOutV1(BaseModel):
    enabled: bool
    stk: STKReminderSettings
    oil: OilReminderSettings
    service_categories: Dict[str, ServiceCategorySettings]
    general: GeneralReminderSettings
    notification: NotificationSettings  # Globální nastavení upozornění


# ==========================
#   AI ENDPOINT
# ==========================

class AIRecordRequestV1(BaseModel):
    shared_secret: str
    user_id: int
    vehicle_id: Optional[int] = None
    message: str


class AIRecordResponseV1(BaseModel):
    status: str
    record_id: Optional[int] = None
    vehicle_id: int
    parsed: dict




