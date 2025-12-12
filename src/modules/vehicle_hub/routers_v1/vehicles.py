"""
Vehicles API v1.0 router
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import Vehicle as VehicleModel, Customer
from .auth import get_current_user, can_access_vehicle
from .schemas import VehicleCreateV1, VehicleUpdateV1, VehicleOutV1

router = APIRouter(prefix="/vehicles", tags=["vehicles-v1"])


@router.post("", response_model=VehicleOutV1)
def create_vehicle(
    vehicle_data: VehicleCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nové vozidlo"""
    # DOČASNĚ ZAKÁZÁNO: assigned_service_id - dokud se neprovede migrace databáze
    # assigned_service_id = None
    # if vehicle_data.assigned_service_id is not None:
    #     service = db.query(Customer).filter(
    #         Customer.id == vehicle_data.assigned_service_id,
    #         Customer.role == "service"
    #     ).first()
    #     if not service:
    #         raise HTTPException(status_code=400, detail="Zadaný servis neexistuje nebo není servisem")
    #     assigned_service_id = service.id
    
    # Vytvořit vozidlo
    vehicle = VehicleModel(
        user_email=current_user.email,
        tenant_id=current_user.tenant_id,  # Nastavit tenant_id z uživatele
        nickname=vehicle_data.nickname,
        brand=vehicle_data.brand,
        model=vehicle_data.model,
        year=vehicle_data.year,
        engine=vehicle_data.engine,
        vin=vehicle_data.vin,
        plate=vehicle_data.plate,
        notes=vehicle_data.notes,
        stk_valid_until=vehicle_data.stk_valid_until,
        tyres_info=vehicle_data.tyres_info,
        insurance_provider=vehicle_data.insurance_provider,
        insurance_valid_until=vehicle_data.insurance_valid_until
        # assigned_service_id=assigned_service_id  # DOČASNĚ ZAKÁZÁNO
    )
    
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    
    return vehicle


@router.get("", response_model=List[VehicleOutV1])
def get_vehicles(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechna vozidla uživatele"""
    try:
        print(f"[VEHICLES] Načítání vozidel pro uživatele: {current_user.email}")
        print(f"[VEHICLES] Tenant ID uživatele: {getattr(current_user, 'tenant_id', 'N/A')}")
        
        # Základní filtr podle emailu
        query = db.query(VehicleModel).filter(
            VehicleModel.user_email == current_user.email
        )
        
        # Přidat filtr podle tenant_id, pokud je nastaven
        # Pokud uživatel nemá tenant_id, zkusit načíst všechna vozidla bez filtru tenant_id
        vehicles = None
        if hasattr(current_user, 'tenant_id') and current_user.tenant_id is not None:
            print(f"[VEHICLES] Filtrování podle tenant_id: {current_user.tenant_id}")
            try:
                vehicles = query.filter(VehicleModel.tenant_id == current_user.tenant_id).all()
            except Exception as tenant_filter_error:
                print(f"[VEHICLES] WARNING: Chyba při filtrování podle tenant_id: {tenant_filter_error}")
                print(f"[VEHICLES] Fallback: Načítám vozidla bez filtru tenant_id")
                vehicles = query.all()
        else:
            print(f"[VEHICLES] Uživatel nemá tenant_id, načítám všechna vozidla bez filtru tenant_id")
            vehicles = query.all()
        
        if vehicles is None:
            vehicles = []
        print(f"[VEHICLES] Nalezeno {len(vehicles)} vozidel")
        
        # Zkontrolovat, zda všechna vozidla mají tenant_id a opravit je
        for vehicle in vehicles:
            if not hasattr(vehicle, 'tenant_id') or vehicle.tenant_id is None:
                print(f"[VEHICLES] WARNING: Vozidlo ID {vehicle.id} nemá tenant_id!")
                # Pokud uživatel má tenant_id, nastavit ho pro vozidlo
                if hasattr(current_user, 'tenant_id') and current_user.tenant_id is not None:
                    print(f"[VEHICLES] Nastavuji tenant_id {current_user.tenant_id} pro vozidlo {vehicle.id}")
                    try:
                        vehicle.tenant_id = current_user.tenant_id
                        db.commit()
                    except Exception as update_error:
                        print(f"[VEHICLES] Chyba při aktualizaci tenant_id: {update_error}")
                        db.rollback()
        
        # Zkusit explicitně serializovat každé vozidlo, abychom zachytili případné chyby
        result = []
        for vehicle in vehicles:
            try:
                # Zkontrolovat, zda vozidlo má všechny potřebné atributy
                if not hasattr(vehicle, 'id'):
                    print(f"[VEHICLES] WARNING: Vozidlo nemá ID, přeskočeno")
                    continue
                
                # Zkusit vytvořit VehicleOutV1 pro validaci
                vehicle_dict = {
                    'id': vehicle.id,
                    'user_email': vehicle.user_email,
                    'nickname': vehicle.nickname,
                    'brand': vehicle.brand,
                    'model': vehicle.model,
                    'year': vehicle.year,
                    'engine': vehicle.engine,
                    'vin': vehicle.vin,
                    'plate': vehicle.plate,
                    'notes': vehicle.notes,
                    'stk_valid_until': vehicle.stk_valid_until,
                    'tyres_info': getattr(vehicle, 'tyres_info', None),
                    'insurance_provider': getattr(vehicle, 'insurance_provider', None),
                    'insurance_valid_until': getattr(vehicle, 'insurance_valid_until', None),
                    'tenant_id': getattr(vehicle, 'tenant_id', None),
                    'created_at': vehicle.created_at
                }
                
                # Validovat pomocí schématu
                VehicleOutV1(**vehicle_dict)
                result.append(vehicle)
            except Exception as veh_error:
                import traceback
                vehicle_id = getattr(vehicle, 'id', 'unknown')
                print(f"[VEHICLES] ERROR: Chyba při validaci vozidla ID {vehicle_id}: {veh_error}")
                traceback.print_exc()
                # Pokračovat s dalšími vozidly místo selhání celého dotazu
        
        print(f"[VEHICLES] Vracím {len(result)} validních vozidel")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e) if str(e) else "Neznámá chyba"
        error_type = type(e).__name__
        print(f"[ERROR] Chyba při načítání vozidel: {error_type}: {error_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {error_type}: {error_msg}")


@router.get("/{vehicle_id}", response_model=VehicleOutV1)
def get_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní vozidlo podle ID"""
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleOutV1)
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje vozidlo"""
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    
    # Aktualizace polí
    if vehicle_data.nickname is not None:
        vehicle.nickname = vehicle_data.nickname
    if vehicle_data.brand is not None:
        vehicle.brand = vehicle_data.brand
    if vehicle_data.model is not None:
        vehicle.model = vehicle_data.model
    if vehicle_data.year is not None:
        vehicle.year = vehicle_data.year
    if vehicle_data.engine is not None:
        vehicle.engine = vehicle_data.engine
    if vehicle_data.vin is not None:
        vehicle.vin = vehicle_data.vin
    if vehicle_data.plate is not None:
        vehicle.plate = vehicle_data.plate
    if vehicle_data.notes is not None:
        vehicle.notes = vehicle_data.notes
    if vehicle_data.stk_valid_until is not None:
        vehicle.stk_valid_until = vehicle_data.stk_valid_until
    if vehicle_data.tyres_info is not None:
        vehicle.tyres_info = vehicle_data.tyres_info
    if vehicle_data.insurance_provider is not None:
        vehicle.insurance_provider = vehicle_data.insurance_provider
    if vehicle_data.insurance_valid_until is not None:
        vehicle.insurance_valid_until = vehicle_data.insurance_valid_until
    
    # DOČASNĚ ZAKÁZÁNO: Aktualizace assigned_service_id - dokud se neprovede migrace databáze
    # if vehicle_data.assigned_service_id is not None:
    #     if vehicle_data.assigned_service_id == 0 or vehicle_data.assigned_service_id == -1:
    #         vehicle.assigned_service_id = None
    #     else:
    #         service = db.query(Customer).filter(
    #             Customer.id == vehicle_data.assigned_service_id,
    #             Customer.role == "service"
    #         ).first()
    #         if not service:
    #             raise HTTPException(status_code=400, detail="Zadaný servis neexistuje nebo není servisem")
    #         vehicle.assigned_service_id = service.id
    # elif hasattr(vehicle_data, 'assigned_service_id') and vehicle_data.assigned_service_id is None:
    #     vehicle.assigned_service_id = None
    
    db.commit()
    db.refresh(vehicle)
    
    return vehicle


@router.delete("/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Smaže vozidlo a všechny související záznamy"""
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu - pouze vlastník může smazat
    if vehicle.user_email != current_user.email and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat toto vozidlo")
    
    try:
        # Smazat související servisní záznamy
        from ..models import ServiceRecord as ServiceRecordModel
        service_records = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        ).all()
        for record in service_records:
            db.delete(record)
        
        # Smazat související připomínky
        from ..models import Reminder
        reminders = db.query(Reminder).filter(
            Reminder.vehicle_id == vehicle_id
        ).all()
        for reminder in reminders:
            db.delete(reminder)
        
        # Smazat související rezervace
        from ..models import Reservation
        reservations = db.query(Reservation).filter(
            Reservation.vehicle_id == vehicle_id
        ).all()
        for reservation in reservations:
            db.delete(reservation)
        
        # Smazat vozidlo
        db.delete(vehicle)
        db.commit()
        
        return {"message": "Vozidlo a všechny související záznamy byly smazány"}
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání vozidla: {str(e)}")

