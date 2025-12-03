"""
Backend server pro TooZ Hub 2
Poskytuje API pro autentizaci, správu uživatelů a vozidel
"""

import sys
from pathlib import Path

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, date

from src.core.config import ALLOWED_ORIGINS, ENVIRONMENT, HOST, PORT
from src.core.security import (
    hash_password, 
    verify_password, 
    needs_rehash,
    create_access_token, 
    decode_access_token
)
from src.modules.vehicle_hub.database import SessionLocal, engine, Base
from src.modules.vehicle_hub.models import Customer, Vehicle as VehicleModel, ServiceRecord as ServiceRecordModel
from src.modules.vehicle_hub.api_vin import decode_vin_api
# Vehicle Decoder Engine router
try:
    from src.modules.vehicle_hub.decoder.router import router as decoder_router
    DECODER_AVAILABLE = True
except ImportError as e:
    print(f"[SERVER] Warning: Vehicle Decoder Engine není dostupný: {e}")
    DECODER_AVAILABLE = False

# Vytvoření tabulek
Base.metadata.create_all(bind=engine)

app = FastAPI(title="TooZ Hub 2 API", version="2.0.0")

# Security
security = HTTPBearer(auto_error=False)

# CORS middleware - veřejný přístup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Veřejný přístup - povolit všechny origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization"],
    expose_headers=["*"],
)

# Include Vehicle Decoder Engine router
if DECODER_AVAILABLE:
    app.include_router(decoder_router)
    print("[SERVER] Vehicle Decoder Engine router zaregistrován: /api/vehicles/decode-vin, /api/vehicles/decode-plate")

# Include File Browser router (dočasný přístup)
try:
    from src.server.file_browser import router as file_browser_router
    app.include_router(file_browser_router)
    print("[SERVER] File Browser zaregistrován: /files/ (dočasný přístup pro kontrolu)")
except ImportError as e:
    print(f"[SERVER] Warning: File Browser není dostupný: {e}")

# ============= MODELY =============

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    ico: Optional[str] = None
    
    class Config:
        from_attributes = True


class VehicleCreate(BaseModel):
    vin: Optional[str] = None
    plate: str
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    engine_code: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: Optional[date] = None  # Datum konce platnosti STK


class VehicleResponse(BaseModel):
    id: int
    vin: Optional[str] = None
    plate: Optional[str] = None
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: Optional[date] = None  # Datum konce platnosti STK
    created_at: datetime
    
    class Config:
        from_attributes = True


class VINDecodeRequest(BaseModel):
    vin: str


class VINDecodeResponse(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    engine_code: Optional[str] = None
    plate: Optional[str] = None
    name: Optional[str] = None
    tyres: list[str] = []
    vehicle_type: Optional[str] = None
    max_power: Optional[str] = None
    tyres_raw: Optional[str] = None
    additional_notes: Optional[str] = None
    inspection_date: Optional[str] = None


class ServiceRecordCreate(BaseModel):
    performed_at: datetime
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    note: Optional[str] = None
    category: Optional[str] = None  # Kategorie servisu (např. "Pravidelná údržba", "Oprava", "Výměna oleje")
    next_service_due_date: Optional[date] = None  # Datum dalšího plánovaného servisu


class ServiceRecordResponse(BaseModel):
    id: int
    vehicle_id: int
    performed_at: datetime
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    note: Optional[str] = None
    category: Optional[str] = None  # Kategorie servisu
    next_service_due_date: Optional[date] = None  # Datum dalšího plánovaného servisu
    
    class Config:
        from_attributes = True


# ============= POMOCNÉ FUNKCE =============

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_email(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_user_email: Optional[str] = Header(None, alias="X-User-Email")
) -> str:
    """
    Získá email uživatele z:
    1. JWT tokenu (Authorization: Bearer <token>)
    2. X-User-Email headeru (legacy/fallback)
    3. user_email query parametru (legacy/fallback)
    """
    # 1. Zkusit JWT token
    if credentials:
        email = decode_access_token(credentials.credentials)
        if email:
            return email
    
    # 2. Zkusit X-User-Email header
    if x_user_email:
        return x_user_email
    
    # 3. Zkusit query parametr
    user_email = request.query_params.get("user_email")
    if user_email:
        return user_email
    
    raise HTTPException(status_code=401, detail="Uživatel není přihlášen")


# ============= AUTH ENDPOINTY =============

@app.post("/user/register", response_model=TokenResponse)
def register_user(user_data: UserRegister, db=Depends(get_db)):
    """Registrace nového uživatele"""
    # Validace hesla
    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    
    # Zkontrolovat, zda uživatel s tímto emailem neexistuje
    existing = db.query(Customer).filter(Customer.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
    
    # Vytvořit nového uživatele s bcrypt hashem
    try:
        hashed_password = hash_password(user_data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    
    customer = Customer(
        email=user_data.email,
        password_hash=hashed_password,
        name=user_data.name,
        ico=user_data.ico,
        dic=user_data.dic,
        street=user_data.street,
        street_number=user_data.street_number,
        city=user_data.city,
        zip=user_data.zip,
        phone=user_data.phone,
    )
    
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    # Vytvořit JWT token
    access_token = create_access_token(data={"sub": customer.email})
    
    return TokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico
        }
    )


@app.post("/user/login", response_model=TokenResponse)
def login_user(login_data: UserLogin, db=Depends(get_db)):
    """Přihlášení uživatele"""
    customer = db.query(Customer).filter(Customer.email == login_data.email).first()
    if not customer:
        raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")
    
    # Ověřit heslo
    if not customer.password_hash:
        raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")
    
    if not verify_password(login_data.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")
    
    # Pokud je potřeba přehashovat (upgrade z SHA256 na bcrypt)
    if needs_rehash(customer.password_hash):
        customer.password_hash = hash_password(login_data.password)
        db.commit()
    
    # Vytvořit JWT token
    access_token = create_access_token(data={"sub": customer.email})
    
    return TokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico
        }
    )


@app.get("/user/me", response_model=UserResponse)
def get_current_user(email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Vrátí aktuálně přihlášeného uživatele"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return customer


@app.get("/user/ares")
def get_ares_data(ico: str):
    """Získání dat z ARES podle IČO"""
    ico_clean = ico.strip().replace(' ', '')
    if not ico_clean.isdigit() or len(ico_clean) != 8:
        raise HTTPException(status_code=400, detail="Neplatné IČO - musí obsahovat 8 číslic")
    
    import requests
    try:
        url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico_clean}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="IČO nenalezeno v ARES")
        raise HTTPException(status_code=response.status_code, detail="Nepodařilo se načíst data z ARES")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout při načítání z ARES") from None
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Chyba při načítání z ARES: {str(e)}") from e


# ============= VOZIDLA ENDPOINTY =============

@app.post("/vehicles/decode-vin", response_model=VINDecodeResponse)
def decode_vin(vin_data: VINDecodeRequest):
    """Dekóduje VIN a vrací informace o vozidle"""
    import logging
    logger = logging.getLogger(__name__)
    try:
        logger.info("[API] Dekódování VIN: %s", vin_data.vin)
        result = decode_vin_api(vin_data.vin)
        return VINDecodeResponse(
            brand=result.get("brand"),
            model=result.get("model"),
            year=result.get("year"),
            engine=result.get("engine"),
            engine_code=result.get("engine_code"),
            plate=result.get("plate"),
            name=result.get("name"),
            tyres=result.get("tyres", []),
            vehicle_type=result.get("vehicle_type"),
            max_power=result.get("max_power"),
            tyres_raw=result.get("tyres_raw"),
            additional_notes=result.get("additional_notes"),
            inspection_date=result.get("inspection_date")
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("[API] Exception: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chyba při dekódování VIN: {str(e)}") from e


@app.post("/vehicles", response_model=VehicleResponse)
def create_vehicle(vehicle_data: VehicleCreate, user_email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Přidá nové vozidlo pro přihlášeného uživatele"""
    vin = None
    if vehicle_data.vin:
        vin = vehicle_data.vin.strip().upper()
        if len(vin) != 17:
            raise HTTPException(status_code=400, detail="Neplatné VIN - musí mít 17 znaků")
        allowed_chars = set('0123456789ABCDEFGHJKLMNPRSTUVWXYZ')
        invalid_chars = set(vin) - allowed_chars
        if invalid_chars:
            raise HTTPException(status_code=400, detail=f"Neplatné VIN - obsahuje nepovolené znaky: {', '.join(sorted(invalid_chars))}")
    
    # Zkontrolovat, zda vozidlo s tímto VIN nebo SPZ už neexistuje
    existing = None
    if vin:
        existing = db.query(VehicleModel).filter(
            VehicleModel.user_email == user_email,
            VehicleModel.vin == vin
        ).first()
    
    if not existing and vehicle_data.plate:
        existing = db.query(VehicleModel).filter(
            VehicleModel.user_email == user_email,
            VehicleModel.plate == vehicle_data.plate
        ).first()
    
    if existing:
        # Aktualizace existujícího vozidla
        existing.nickname = vehicle_data.name
        existing.brand = vehicle_data.brand
        existing.model = vehicle_data.model
        existing.year = vehicle_data.year
        existing.engine = vehicle_data.engine
        existing.vin = vin
        existing.plate = vehicle_data.plate
        existing.notes = vehicle_data.notes
        existing.stk_valid_until = vehicle_data.stk_valid_until
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Vytvoření nového vozidla
        vehicle = VehicleModel(
            user_email=user_email,
            nickname=vehicle_data.name,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            engine=vehicle_data.engine,
            vin=vin,
            plate=vehicle_data.plate,
            notes=vehicle_data.notes,
            stk_valid_until=vehicle_data.stk_valid_until
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        return vehicle


@app.get("/vehicles", response_model=list[VehicleResponse])
def get_vehicles(user_email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Vrací všechna vozidla přihlášeného uživatele"""
    vehicles = db.query(VehicleModel).filter(
        VehicleModel.user_email == user_email
    ).all()
    return vehicles


@app.get("/vehicles/{vehicle_id}", response_model=VehicleResponse)
def get_vehicle(vehicle_id: int, user_email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Vrací konkrétní vozidlo podle ID"""
    vehicle = db.query(VehicleModel).filter(
        VehicleModel.id == vehicle_id,
        VehicleModel.user_email == user_email
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    return vehicle


@app.delete("/vehicles/{vehicle_id}")
def delete_vehicle(vehicle_id: int, user_email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Smaže vozidlo"""
    vehicle = db.query(VehicleModel).filter(
        VehicleModel.id == vehicle_id,
        VehicleModel.user_email == user_email
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    db.delete(vehicle)
    db.commit()
    return {"message": "Vozidlo bylo smazáno"}


# ============= SERVISNÍ ZÁZNAMY ENDPOINTY =============

@app.post("/vehicles/{vehicle_id}/service-records", response_model=ServiceRecordResponse)
def create_service_record(
    vehicle_id: int,
    record_data: ServiceRecordCreate,
    user_email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Přidá nový servisní záznam k vozidlu"""
    # Ověřit, že vozidlo patří uživateli
    vehicle = db.query(VehicleModel).filter(
        VehicleModel.id == vehicle_id,
        VehicleModel.user_email == user_email
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Vytvořit servisní záznam
    service_record = ServiceRecordModel(
        vehicle_id=vehicle_id,
        performed_at=record_data.performed_at,
        mileage=record_data.mileage,
        description=record_data.description,
        price=record_data.price,
        note=record_data.note,
        category=record_data.category,
        next_service_due_date=record_data.next_service_due_date
    )
    
    db.add(service_record)
    db.commit()
    db.refresh(service_record)
    
    return service_record


@app.get("/vehicles/{vehicle_id}/service-records", response_model=list[ServiceRecordResponse])
def get_service_records(
    vehicle_id: int,
    user_email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Vrací všechny servisní záznamy pro vozidlo"""
    # Ověřit, že vozidlo patří uživateli
    vehicle = db.query(VehicleModel).filter(
        VehicleModel.id == vehicle_id,
        VehicleModel.user_email == user_email
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Načíst servisní záznamy
    records = db.query(ServiceRecordModel).filter(
        ServiceRecordModel.vehicle_id == vehicle_id
    ).order_by(ServiceRecordModel.performed_at.desc()).all()
    
    return records


@app.delete("/service-records/{record_id}")
def delete_service_record(
    record_id: int,
    user_email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Smaže servisní záznam"""
    # Načíst záznam a ověřit, že vozidlo patří uživateli
    record = db.query(ServiceRecordModel).filter(
        ServiceRecordModel.id == record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
    
    vehicle = db.query(VehicleModel).filter(
        VehicleModel.id == record.vehicle_id,
        VehicleModel.user_email == user_email
    ).first()
    
    if not vehicle:
        raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat tento záznam")
    
    db.delete(record)
    db.commit()
    return {"message": "Servisní záznam byl smazán"}


# ============= STATIC FILES =============

try:
    web_path = Path(__file__).parent.parent.parent / "web"
    if web_path.exists():
        app.mount("/web", StaticFiles(directory=str(web_path), html=True), name="web")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount web directory: {e}")

# ============= PUBLIC FILE SERVER =============

# Veřejná cesta k sdíleným souborům
public_path = Path(__file__).parent.parent.parent / "public_share"
public_path.mkdir(parents=True, exist_ok=True)

@app.get("/public/", response_class=HTMLResponse)
@app.get("/public/{path:path}", response_class=HTMLResponse)
def public_file_list(path: str = ""):
    """Zobrazí seznam souborů a složek v public_share"""
    # Normalizace cesty - odstranit koncové lomítko
    path_clean = path.strip("/") if path else ""
    
    # Rozdělení na části
    path_parts = [p for p in path_clean.split("/") if p and p != "." and p != ".."]
    target_path = public_path
    if path_parts:
        target_path = public_path / "/".join(path_parts)
    
    # Bezpečnostní kontrola - zabránit directory traversal
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(public_path.resolve())):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
    except:
        raise HTTPException(status_code=404, detail="Cesta nenalezena")
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")
    
    # Pokud je to soubor, přesměrujeme na static files
    if target_path.is_file():
        return FileResponse(target_path)
    
    # Generování HTML seznamu pro složku
    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if item.name.startswith('.'):
                continue  # Skrýt skryté soubory
            
            rel_path = str(item.relative_to(public_path)).replace("\\", "/")
            size = ""
            if item.is_file():
                size_bytes = item.stat().st_size
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes / 1024:.1f} KB"
                else:
                    size = f"{size_bytes / (1024 * 1024):.1f} MB"
            
            items.append({
                "name": item.name,
                "path": rel_path,
                "is_dir": item.is_dir(),
                "size": size,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Přístup zamítnut")
    
    # Breadcrumb navigace
    breadcrumb = '<a href="/public/">🏠 Kořen</a>'
    current_breadcrumb_path = ""
    for part in path_parts:
        current_breadcrumb_path += "/" + part
        breadcrumb += f' / <a href="/public{current_breadcrumb_path}/">{part}</a>'
    
    # HTML šablona
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Veřejné soubory - TooZ Hub 2</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2em;
                margin-bottom: 10px;
            }}
            .breadcrumb {{
                background: #f8f9fa;
                padding: 15px 30px;
                border-bottom: 1px solid #dee2e6;
                font-size: 14px;
            }}
            .breadcrumb a {{
                color: #667eea;
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            .file-list {{
                padding: 30px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th {{
                background: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
            }}
            td {{
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }}
            tr:hover {{
                background: #f8f9fa;
            }}
            .folder {{
                color: #ff9800;
                font-weight: bold;
            }}
            .folder::before {{
                content: "📁 ";
            }}
            .file {{
                color: #2196F3;
            }}
            .file::before {{
                content: "📄 ";
            }}
            a {{
                color: inherit;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .size {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .modified {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .empty {{
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 Veřejné soubory</h1>
                <p>TooZ Hub 2 - Public File Server</p>
            </div>
            <div class="breadcrumb">
                {breadcrumb}
            </div>
            <div class="file-list">
    """
    
    if items:
        html += """
                <table>
                    <thead>
                        <tr>
                            <th>Název</th>
                            <th>Velikost</th>
                            <th>Upraveno</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for item in items:
            if item["is_dir"]:
                link = f'/public/{item["path"]}/'
                html += f"""
                        <tr>
                            <td class="folder"><a href="{link}">{item["name"]}</a></td>
                            <td class="size">-</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """
            else:
                link = f'/public/{item["path"]}'
                html += f"""
                        <tr>
                            <td class="file"><a href="{link}" target="_blank">{item["name"]}</a></td>
                            <td class="size">{item["size"]}</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """
        
        html += """
                    </tbody>
                </table>
        """
    else:
        html += """
                <div class="empty">
                    <p>📂 Tato složka je prázdná</p>
                </div>
        """
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

# Mount static files pro konkrétní soubory (pod endpointy, aby neměl přednost před route)
try:
    if public_path.exists():
        app.mount("/public", StaticFiles(directory=str(public_path)), name="public_static")
        print(f"[SERVER] Public file server zaregistrován: /public/ (directory: {public_path})")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount public directory: {e}")


# ============= ROOT & HEALTH =============

@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "TooZ Hub 2 API",
        "version": "2.0.0",
        "environment": ENVIRONMENT,
        "features": {
            "jwt_auth": True,
            "bcrypt_passwords": True,
            "vehicles": True,
            "vin_decoder": True
        },
        "endpoints": {
            "register": "/user/register",
            "login": "/user/login",
            "me": "/user/me",
            "ares": "/user/ares?ico=ICO",
            "vehicles": "/vehicles",
            "decode_vin": "/vehicles/decode-vin"
        },
        "web_interface": "/web/index.html" if Path(__file__).parent.parent.parent.joinpath("web").exists() else None
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "TooZ Hub 2 API",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    
    print(f"[SERVER] Spouštím server na {HOST}:{PORT}")
    print(f"[SERVER] Režim: {ENVIRONMENT}")
    print(f"[SERVER] CORS origins: {ALLOWED_ORIGINS}")
    print("")
    
    uvicorn.run(app, host=HOST, port=PORT)
