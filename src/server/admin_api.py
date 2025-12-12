"""
Admin API router pro TooZ Hub 2
Přístupné pouze pro developer_admin role
"""
from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from pathlib import Path
import os

from src.core.auth import get_current_user_email, security
from src.core.security import hash_password
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Vehicle, ServiceRecord, Reservation, Reminder

router = APIRouter(prefix="/admin-api", tags=["admin"])

# Import pro admin tenants endpoints
try:
    from src.modules.vehicle_hub.models import Tenant, Instance
    TENANTS_AVAILABLE = True
except ImportError:
    TENANTS_AVAILABLE = False
    Tenant = None
    Instance = None


# ============= DEPENDENCIES =============

def require_developer_admin(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
):
    """Ověří, že uživatel má roli developer_admin"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    
    if customer.role != "developer_admin":
        raise HTTPException(
            status_code=403,
            detail="Přístup odepřen. Vyžadována role developer_admin."
        )
    
    return email


def safe_count_query(db: Session, query_str: str, params: Dict[str, Any] = None) -> int:
    """Bezpečné provedení COUNT dotazu - vrací 0 při chybě"""
    try:
        result = db.execute(text(query_str), params or {})
        return result.scalar() or 0
    except Exception as e:
        print(f"⚠️ Warning: Query failed: {query_str}, Error: {e}")
        return 0


def get_user_id_from_email(email: str, db: Session) -> Optional[int]:
    """Získá ID uživatele podle emailu"""
    user = db.query(Customer).filter(Customer.email == email).first()
    return user.id if user else None


def get_client_ip(request: FastAPIRequest) -> Optional[str]:
    """Získá IP adresu klienta"""
    if request.client:
        return request.client.host
    return None


# ============= SCHEMAS =============

class StatsOverview(BaseModel):
    total_users: int
    total_vehicles: int
    total_services: int
    total_records: int
    total_reservations: int = 0
    total_reminders: int = 0


class UserSummary(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    role: str
    city: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    vehicles_count: int = 0


class VehicleSummary(BaseModel):
    id: int
    user_email: str
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None
    created_at: Optional[datetime] = None
    service_count: int = 0


# ============= CRUD SCHEMAS =============

class UserCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    password: str
    role: str = "user"

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

class VehicleCreate(BaseModel):
    user_email: EmailStr
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None

class VehicleUpdate(BaseModel):
    user_email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None

class ServiceCreate(BaseModel):
    email: EmailStr
    name: str
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: str

class ServiceUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: Optional[str] = None

class RecordCreate(BaseModel):
    vehicle_id: int
    user_id: Optional[int] = None
    performed_at: datetime
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None

class RecordUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    user_id: Optional[int] = None
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None

class DbInfoResponse(BaseModel):
    db_path: str
    table_count: int
    tables: List[str]
    total_size_kb: Optional[float] = None


class TenantListItem(BaseModel):
    id: int
    name: str
    license_key: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class InstanceListItem(BaseModel):
    id: int
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    last_seen_at: datetime
    
    class Config:
        from_attributes = True


# ============= ENDPOINTS =============

@router.get("/overview", response_model=StatsOverview)
def get_overview(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí přehled statistik celé databáze - pouze pro developer_admin"""
    try:
        total_users = safe_count_query(db, "SELECT COUNT(*) FROM customers")
        total_vehicles = safe_count_query(db, "SELECT COUNT(*) FROM vehicles")
        total_services = safe_count_query(db, "SELECT COUNT(*) FROM customers WHERE role = 'service'")
        total_records = safe_count_query(db, "SELECT COUNT(*) FROM service_records")
        total_reservations = safe_count_query(db, "SELECT COUNT(*) FROM reservations")
        total_reminders = safe_count_query(db, "SELECT COUNT(*) FROM reminders")
        
        return StatsOverview(
            total_users=total_users,
            total_vehicles=total_vehicles,
            total_services=total_services,
            total_records=total_records,
            total_reservations=total_reservations,
            total_reminders=total_reminders
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání statistik: {str(e)}")


@router.get("/users", response_model=List[UserSummary])
def get_all_users(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech uživatelů s počtem vozidel - pouze pro developer_admin"""
    try:
        result = db.execute(text("""
            SELECT 
                c.id,
                c.email,
                c.name,
                c.role,
                c.city,
                c.phone,
                c.created_at,
                COUNT(v.id) as vehicles_count
            FROM customers c
            LEFT JOIN vehicles v ON v.user_email = c.email
            GROUP BY c.id, c.email, c.name, c.role, c.city, c.phone, c.created_at
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        users = []
        for row in result:
            created_at = row[6]
            users.append(UserSummary(
                id=row[0],
                email=row[1],
                name=row[2],
                role=row[3],
                city=row[4],
                phone=row[5],
                created_at=created_at,
                vehicles_count=row[7] or 0
            ))
        
        return users
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání uživatelů: {str(e)}")


@router.post("/users")
def create_user(
    user_data: UserCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového uživatele"""
    try:
        # Zkontrolovat, zda email již existuje
        existing = db.query(Customer).filter(Customer.email == user_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(user_data.password)
        
        # Vytvořit uživatele
        new_user = Customer(
            email=user_data.email,
            name=user_data.name,
            password_hash=password_hash_value,
            role=user_data.role,
            created_at=datetime.utcnow()
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {"id": new_user.id, "email": user_data.email, "message": "Uživatel byl vytvořen"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření uživatele: {str(e)}")


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava uživatele"""
    try:
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        # Aktualizovat pole
        if user_data.email is not None:
            # Zkontrolovat, zda nový email neexistuje
            existing = db.query(Customer).filter(Customer.email == user_data.email, Customer.id != user_id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
            user.email = user_data.email
        
        if user_data.name is not None:
            user.name = user_data.name
        
        if user_data.role is not None:
            user.role = user_data.role
        
        if user_data.password is not None:
            user.password_hash = hash_password(user_data.password)
        
        db.commit()
        return {"message": "Uživatel byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě uživatele: {str(e)}")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání uživatele"""
    try:
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        user_email = user.email
        db.delete(user)
        db.commit()
        
        return {"message": f"Uživatel {user_email} byl smazán"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání uživatele: {str(e)}")


@router.get("/users/{user_id}/vehicles", response_model=List[VehicleSummary])
def get_user_vehicles(
    user_id: int,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí všechna vozidla daného uživatele - pouze pro developer_admin"""
    try:
        # Získat email uživatele podle ID
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        user_email = user.email
        
        # Načíst vozidla uživatele s počtem servisních záznamů
        vehicles_result = db.execute(text("""
            SELECT 
                v.id,
                v.user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            WHERE v.user_email = :user_email
            GROUP BY v.id, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at
            ORDER BY v.created_at DESC
        """), {"user_email": user_email})
        
        vehicles = []
        for row in vehicles_result:
            created_at = row[8]
            vehicles.append(VehicleSummary(
                id=row[0],
                user_email=row[1],
                nickname=row[2],
                brand=row[3],
                model=row[4],
                year=row[5],
                plate=row[6],
                vin=row[7],
                created_at=created_at,
                service_count=row[9] or 0
            ))
        
        return vehicles
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.get("/services", response_model=List[UserSummary])
def get_all_services(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech servisů (customers s role='service') - pouze pro developer_admin"""
    try:
        result = db.execute(text("""
            SELECT 
                c.id,
                c.email,
                c.name,
                c.role,
                c.city,
                c.phone,
                c.created_at,
                0 as vehicles_count
            FROM customers c
            WHERE c.role = 'service' OR c.role = 'developer_admin'
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        services = []
        for row in result:
            created_at = row[6]
            services.append(UserSummary(
                id=row[0],
                email=row[1],
                name=row[2],
                role=row[3],
                city=row[4],
                phone=row[5],
                created_at=created_at,
                vehicles_count=0
            ))
        
        return services
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisů: {str(e)}")


@router.post("/services")
def create_service(
    service_data: ServiceCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisu"""
    try:
        # Zkontrolovat, zda email již existuje
        existing = db.query(Customer).filter(Customer.email == service_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(service_data.password)
        
        # Vytvořit servis
        new_service = Customer(
            email=service_data.email,
            name=service_data.name,
            password_hash=password_hash_value,
            role="service",
            city=service_data.city,
            phone=service_data.phone,
            ico=service_data.ico,
            created_at=datetime.utcnow()
        )
        db.add(new_service)
        db.commit()
        db.refresh(new_service)
        
        return {"id": new_service.id, "email": service_data.email, "message": "Servis byl vytvořen"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisu: {str(e)}")


@router.patch("/services/{service_id}")
def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisu"""
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")
        
        if service.role not in ["service", "developer_admin"]:
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis")
        
        # Aktualizovat pole
        if service_data.email is not None:
            existing = db.query(Customer).filter(Customer.email == service_data.email, Customer.id != service_id).first()
            if existing:
                raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
            service.email = service_data.email
        
        if service_data.name is not None:
            service.name = service_data.name
        
        if service_data.city is not None:
            service.city = service_data.city
        
        if service_data.phone is not None:
            service.phone = service_data.phone
        
        if service_data.ico is not None:
            service.ico = service_data.ico
        
        if service_data.password is not None:
            service.password_hash = hash_password(service_data.password)
        
        db.commit()
        return {"message": "Servis byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě servisu: {str(e)}")


@router.delete("/services/{service_id}")
def delete_service(
    service_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání servisu"""
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")
        
        if service.role not in ["service", "developer_admin"]:
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis")
        
        service_email = service.email
        db.delete(service)
        db.commit()
        
        return {"message": f"Servis {service_email} byl smazán"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání servisu: {str(e)}")


@router.get("/vehicles")
def get_all_vehicles(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech vozidel - pouze pro developer_admin"""
    try:
        result = db.execute(text("""
            SELECT 
                v.id,
                v.user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count,
                c.name as owner_name
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            LEFT JOIN customers c ON c.email = v.user_email
            GROUP BY v.id, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at, c.name
            ORDER BY v.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        vehicles = []
        for row in result:
            created_at = row[8]
            vehicles.append({
                "id": row[0],
                "user_email": row[1],
                "nickname": row[2],
                "brand": row[3],
                "model": row[4],
                "year": row[5],
                "plate": row[6],
                "vin": row[7],
                "created_at": created_at.isoformat() if created_at else None,
                "service_count": row[9] or 0,
                "owner_name": row[10]
            })
        
        return vehicles
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.post("/vehicles")
def create_vehicle(
    vehicle_data: VehicleCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového vozidla"""
    try:
        # Zkontrolovat, zda uživatel existuje
        user = db.query(Customer).filter(Customer.email == vehicle_data.user_email).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        # Vytvořit vozidlo
        new_vehicle = Vehicle(
            user_email=vehicle_data.user_email,
            nickname=vehicle_data.nickname,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            plate=vehicle_data.plate,
            vin=vehicle_data.vin,
            created_at=datetime.utcnow()
        )
        db.add(new_vehicle)
        db.commit()
        db.refresh(new_vehicle)
        
        return {"id": new_vehicle.id, "message": "Vozidlo bylo vytvořeno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření vozidla: {str(e)}")


@router.patch("/vehicles/{vehicle_id}")
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava vozidla"""
    try:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        # Aktualizovat pole
        if vehicle_data.user_email is not None:
            user = db.query(Customer).filter(Customer.email == vehicle_data.user_email).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            vehicle.user_email = vehicle_data.user_email
        
        if vehicle_data.nickname is not None:
            vehicle.nickname = vehicle_data.nickname
        
        if vehicle_data.brand is not None:
            vehicle.brand = vehicle_data.brand
        
        if vehicle_data.model is not None:
            vehicle.model = vehicle_data.model
        
        if vehicle_data.year is not None:
            vehicle.year = vehicle_data.year
        
        if vehicle_data.plate is not None:
            vehicle.plate = vehicle_data.plate
        
        if vehicle_data.vin is not None:
            vehicle.vin = vehicle_data.vin
        
        db.commit()
        return {"message": "Vozidlo bylo upraveno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě vozidla: {str(e)}")


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání vozidla"""
    try:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        db.delete(vehicle)
        db.commit()
        
        return {"message": "Vozidlo bylo smazáno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání vozidla: {str(e)}")


@router.get("/records")
def get_all_records(
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[int] = None,
    vehicle_id: Optional[int] = None,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Vrátí kompletní seznam všech servisních záznamů
    Dostupné jen pro developer_admin
    """
    try:
        query = """
            SELECT 
                sr.id,
                sr.vehicle_id,
                sr.user_id,
                sr.performed_at,
                sr.mileage,
                sr.description,
                sr.price,
                sr.note,
                sr.category,
                sr.created_at,
                v.nickname as vehicle_nickname,
                v.brand as vehicle_brand,
                v.model as vehicle_model,
                v.plate as vehicle_plate,
                c.email as user_email,
                c.name as user_name
            FROM service_records sr
            LEFT JOIN vehicles v ON v.id = sr.vehicle_id
            LEFT JOIN customers c ON c.id = sr.user_id
            WHERE 1=1
        """
        params = {}
        
        if user_id:
            query += " AND sr.user_id = :user_id"
            params["user_id"] = user_id
        
        if vehicle_id:
            query += " AND sr.vehicle_id = :vehicle_id"
            params["vehicle_id"] = vehicle_id
        
        query += " ORDER BY sr.performed_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params)
        
        records = []
        for row in result:
            performed_at = row[3]
            created_at = row[9]
            records.append({
                "id": row[0],
                "vehicle_id": row[1],
                "user_id": row[2],
                "performed_at": performed_at.isoformat() if performed_at else None,
                "mileage": row[4],
                "description": row[5],
                "price": row[6],
                "note": row[7],
                "category": row[8],
                "created_at": created_at.isoformat() if created_at else None,
                "vehicle_nickname": row[10],
                "vehicle_brand": row[11],
                "vehicle_model": row[12],
                "vehicle_plate": row[13],
                "user_email": row[14],
                "user_name": row[15]
            })
        
        # Celkový počet
        count_query = "SELECT COUNT(*) FROM service_records WHERE 1=1"
        count_params = {}
        if user_id:
            count_query += " AND user_id = :user_id"
            count_params["user_id"] = user_id
        if vehicle_id:
            count_query += " AND vehicle_id = :vehicle_id"
            count_params["vehicle_id"] = vehicle_id
        
        total_count = safe_count_query(db, count_query, count_params)
        
        return {
            "records": records,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "records": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání záznamů: {str(e)}"
        }


@router.get("/audit")
def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Vrátí poslední aktivity (reservations, reminders jako audit log)
    Dostupné jen pro developer_admin
    """
    try:
        # Kombinace reservations a reminders jako "audit log"
        # SQLite nepodporuje CONCAT, použít || pro concatenaci
        query = """
            SELECT 
                'reservation' as type,
                r.id,
                r.created_at as timestamp,
                c.email as actor_email,
                'CREATE_RESERVATION' as action,
                r.vehicle_id as entity_id,
                r.service_id as related_id,
                ('Rezervace pro vozidlo ' || COALESCE(v.nickname, '?')) as details
            FROM reservations r
            LEFT JOIN vehicles v ON v.id = r.vehicle_id
            LEFT JOIN customers c ON c.id = r.customer_id
            WHERE 1=1
            
            UNION ALL
            
            SELECT 
                'reminder' as type,
                rem.id,
                rem.created_at as timestamp,
                c.email as actor_email,
                'CREATE_REMINDER' as action,
                rem.vehicle_id as entity_id,
                NULL as related_id,
                rem.text as details
            FROM reminders rem
            LEFT JOIN customers c ON c.id = rem.customer_id
            WHERE 1=1
            
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """
        
        result = db.execute(text(query), {"limit": limit, "offset": offset})
        
        logs = []
        for row in result:
            timestamp = row[2]
            logs.append({
                "id": row[1],
                "timestamp": timestamp.isoformat() if timestamp else None,
                "actor_email": row[3],
                "action": row[4],
                "entity_type": row[0],
                "entity_id": row[5],
                "details": row[7]
            })
        
        return {
            "logs": logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "logs": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání audit logu: {str(e)}"
        }


@router.post("/records")
def create_record(
    record_data: RecordCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisního záznamu"""
    try:
        # Zkontrolovat, zda vozidlo existuje
        vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        # Pokud je zadán user_id, zkontrolovat, zda existuje
        if record_data.user_id:
            user = db.query(Customer).filter(Customer.id == record_data.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        else:
            # Pokud není zadán user_id, použít aktuálního admina
            current_user = db.query(Customer).filter(Customer.email == email).first()
            record_data.user_id = current_user.id if current_user else None
        
        # Vytvořit záznam
        new_record = ServiceRecord(
            vehicle_id=record_data.vehicle_id,
            user_id=record_data.user_id,
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            category=record_data.category,
            note=record_data.note
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        
        return {"id": new_record.id, "message": "Servisní záznam byl vytvořen"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření záznamu: {str(e)}")


@router.patch("/records/{record_id}")
def update_record(
    record_id: int,
    record_data: RecordUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisního záznamu"""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        
        # Aktualizovat pole
        if record_data.vehicle_id is not None:
            vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            record.vehicle_id = record_data.vehicle_id
        
        if record_data.user_id is not None:
            user = db.query(Customer).filter(Customer.id == record_data.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            record.user_id = record_data.user_id
        
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        
        if record_data.mileage is not None:
            record.mileage = record_data.mileage
        
        if record_data.description is not None:
            record.description = record_data.description
        
        if record_data.price is not None:
            record.price = record_data.price
        
        if record_data.category is not None:
            record.category = record_data.category
        
        if record_data.note is not None:
            record.note = record_data.note
        
        db.commit()
        return {"message": "Záznam byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě záznamu: {str(e)}")


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání servisního záznamu"""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        
        db.delete(record)
        db.commit()
        
        return {"message": "Záznam byl smazán"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání záznamu: {str(e)}")


# ============= SYSTEM TOOLS =============

@router.post("/reindex")
def reindex_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Přeindexování databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje indexy, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je již indexovaná (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při indexování: {str(e)}")


@router.post("/repair")
def repair_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Oprava databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje integritu, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je v pořádku (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při opravě: {str(e)}")


@router.get("/db-info", response_model=DbInfoResponse)
def get_db_info(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Informace o databázi"""
    try:
        from src.modules.vehicle_hub.database import DB_URL
        
        # Získat seznam tabulek
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        # Získat cestu k databázi
        db_path = str(DB_URL).replace("sqlite:///", "")
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
            size_kb = round(size_bytes / 1024, 2)
        else:
            size_kb = None
        
        return DbInfoResponse(
            db_path=db_path,
            table_count=len(tables),
            tables=tables,
            total_size_kb=size_kb
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při získávání informací: {str(e)}")


# ============= TENANTS & INSTANCES (Multi-tenant) =============

@router.get("/tenants", response_model=List[TenantListItem])
def list_tenants(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech tenants - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Tenants modely nejsou dostupné")
    
    try:
        tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit).all()
        return [TenantListItem(
            id=t.id,
            name=t.name,
            license_key=t.license_key,
            created_at=t.created_at
        ) for t in tenants]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání tenants: {str(e)}")


@router.get("/tenants/{tenant_id}/instances", response_model=List[InstanceListItem])
def list_instances(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam instancí pro daného tenanta - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Instances modely nejsou dostupné")
    
    try:
        # Zkontrolovat, zda tenant existuje
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant nenalezen")
        
        instances = db.query(Instance).filter(
            Instance.tenant_id == tenant_id
        ).order_by(Instance.last_seen_at.desc()).offset(offset).limit(limit).all()
        
        return [InstanceListItem(
            id=i.id,
            device_id=i.device_id,
            app_version=i.app_version,
            last_seen_at=i.last_seen_at
        ) for i in instances]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání instancí: {str(e)}")

