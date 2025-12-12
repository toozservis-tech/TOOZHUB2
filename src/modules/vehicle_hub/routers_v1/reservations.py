"""
Reservations API v1.0 router (Objednávky do servisu)
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from ..database import get_db
from ..models import Reservation as ReservationModel, Vehicle as VehicleModel, Customer
from .auth import get_current_user, require_role
from .schemas import ReservationCreateV1, ReservationUpdateV1, ReservationOutV1
from ..email_notifications import send_reservation_created_email, send_reservation_status_email

router = APIRouter(prefix="/reservations", tags=["reservations-v1"])


@router.post("", response_model=ReservationOutV1)
def create_reservation(
    reservation_data: ReservationCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří novou rezervaci"""
    # Ověřit, že vozidlo existuje a patří uživateli (nebo má service přístup)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == reservation_data.vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Pro uživatele (role user) - rezervace musí být pro jeho vozidlo
    if current_user.role == "user":
        if vehicle.user_email != current_user.email:
            raise HTTPException(status_code=403, detail="Nemůžete vytvořit rezervaci pro cizí vozidlo")
        customer_id = current_user.id
    else:
        # Pro service/admin - použít customer_id z vozidla
        customer = db.query(Customer).filter(Customer.email == vehicle.user_email).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Zákazník nenalezen")
        customer_id = customer.id
    
    # Kontrola kolize časů (základní)
    existing = db.query(ReservationModel).filter(
        ReservationModel.service_id == reservation_data.service_id,
        ReservationModel.start_datetime == reservation_data.start_datetime,
        ReservationModel.status != "CANCELLED"
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Rezervace na tento čas již existuje")
    
    # Vytvořit rezervaci
    reservation = ReservationModel(
        service_id=reservation_data.service_id,
        customer_id=customer_id,
        vehicle_id=reservation_data.vehicle_id,
        service_type=reservation_data.service_type,
        note=reservation_data.note,
        start_datetime=reservation_data.start_datetime,
        end_datetime=reservation_data.end_datetime,
        status="PENDING"
    )
    
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    
    # Odeslat e-mail notifikace (na pozadí, neblokovat odpověď)
    try:
        send_reservation_created_email(db, reservation)
    except Exception as e:
        print(f"[RESERVATION] Chyba při odesílání e-mailu: {e}")
        # Nevyvolat chybu - rezervace byla úspěšně vytvořena
    
    return reservation


@router.get("/my", response_model=List[ReservationOutV1])
def get_my_reservations(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací rezervace aktuálního uživatele (role user)"""
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Tento endpoint je pouze pro uživatele")
    
    reservations = db.query(ReservationModel).filter(
        ReservationModel.customer_id == current_user.id
    ).order_by(ReservationModel.start_datetime.desc()).all()
    
    return reservations


@router.get("/service", response_model=List[ReservationOutV1])
def get_service_reservations(
    current_user: Customer = Depends(require_role("service")),
    db: Session = Depends(get_db)
):
    """Vrací rezervace pro servis (role service)"""
    reservations = db.query(ReservationModel).filter(
        ReservationModel.service_id == current_user.id
    ).order_by(ReservationModel.start_datetime.desc()).all()
    
    return reservations


@router.get("/{reservation_id}", response_model=ReservationOutV1)
def get_reservation(
    reservation_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")
    
    # Kontrola přístupu
    if current_user.role == "user":
        if reservation.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")
    elif current_user.role == "service":
        if reservation.service_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")
    
    return reservation


@router.put("/{reservation_id}", response_model=ReservationOutV1)
def update_reservation(
    reservation_id: int,
    reservation_data: ReservationUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")
    
    # Kontrola přístupu a oprávnění
    if current_user.role == "user":
        if reservation.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")
        # Uživatel může změnit pouze note a některá pole, ne status
        if reservation_data.status is not None:
            raise HTTPException(status_code=403, detail="Uživatel nemůže změnit status rezervace")
    elif current_user.role == "service":
        if reservation.service_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")
    
    # Uložit původní status pro kontrolu změny
    old_status = reservation.status
    
    # Aktualizace polí
    if reservation_data.service_type is not None:
        reservation.service_type = reservation_data.service_type
    if reservation_data.note is not None:
        reservation.note = reservation_data.note
    if reservation_data.start_datetime is not None:
        reservation.start_datetime = reservation_data.start_datetime
    if reservation_data.end_datetime is not None:
        reservation.end_datetime = reservation_data.end_datetime
    if reservation_data.status is not None and current_user.role != "user":
        reservation.status = reservation_data.status
    
    db.commit()
    db.refresh(reservation)
    
    # Odeslat e-mail při změně statusu (CONFIRMED nebo CANCELLED)
    if reservation_data.status is not None and old_status != reservation.status:
        try:
            send_reservation_status_email(db, reservation, old_status)
        except Exception as e:
            print(f"[RESERVATION] Chyba při odesílání e-mailu: {e}")
            # Nevyvolat chybu - rezervace byla úspěšně aktualizována
    
    return reservation


@router.delete("/{reservation_id}")
def delete_reservation(
    reservation_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Smaže rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")
    
    # Kontrola přístupu
    if current_user.role == "user":
        if reservation.customer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat tuto rezervaci")
    elif current_user.role == "service":
        if reservation.service_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat tuto rezervaci")
    
    db.delete(reservation)
    db.commit()
    
    return {"message": "Rezervace byla smazána"}
