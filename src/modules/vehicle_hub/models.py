from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    # identita / login
    email = Column(String, unique=True, index=True, nullable=False)

    # fakturační / kontaktní údaje
    name = Column(String, nullable=True)          # jméno / název
    ico = Column(String, nullable=True)           # IČO (pro ARES)
    street = Column(String, nullable=True)
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

    created_at = Column(DateTime, default=datetime.utcnow)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String, index=True, nullable=False)
    nickname = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    engine = Column(String, nullable=True)
    vin = Column(String, nullable=True)
    plate = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship(
        "ServiceRecord",
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), index=True, nullable=False)
    performed_at = Column(DateTime, default=datetime.utcnow)
    mileage = Column(Integer, nullable=True)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    note = Column(String, nullable=True)

    vehicle = relationship("Vehicle", back_populates="records")

