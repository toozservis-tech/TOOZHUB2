from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ==========================
#   ZÁKAZNÍK (profil)
# ==========================

class CustomerCreate(BaseModel):
    email: EmailStr

    name: Optional[str] = None
    ico: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None

    notify_email: bool = True
    notify_sms: bool = False

    notify_stk: bool = True
    notify_oil: bool = True
    notify_general: bool = True


class CustomerOut(BaseModel):
    id: int
    email: EmailStr

    name: Optional[str]
    ico: Optional[str]
    street: Optional[str]
    city: Optional[str]
    zip: Optional[str]
    phone: Optional[str]

    notify_email: bool
    notify_sms: bool
    notify_stk: bool
    notify_oil: bool
    notify_general: bool

    created_at: datetime

    class Config:
        from_attributes = True   # Pydantic v2


# ==========================
#   VOZIDLA
# ==========================

class VehicleCreate(BaseModel):
    user_email: EmailStr
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None


class VehicleOut(BaseModel):
    id: int
    user_email: EmailStr
    nickname: Optional[str]
    brand: Optional[str]
    model: Optional[int] | Optional[str]  # tolerujeme staré typy
    year: Optional[int]
    engine: Optional[str]
    vin: Optional[str]
    plate: Optional[str]

    class Config:
        from_attributes = True


# ==========================
#   SERVISNÍ ZÁZNAMY
# ==========================

class ServiceRecordCreate(BaseModel):
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    note: Optional[str] = None


class ServiceRecordOut(BaseModel):
    id: int
    vehicle_id: int
    performed_at: datetime
    mileage: Optional[int]
    description: str
    price: Optional[float]
    note: Optional[str]

    class Config:
        from_attributes = True

