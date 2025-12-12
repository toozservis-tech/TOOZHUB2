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
from datetime import datetime, date, timedelta

from src.core.config import ALLOWED_ORIGINS, ENVIRONMENT, HOST, PORT, JWT_SECRET_KEY
from src.core.security import (
    hash_password, 
    verify_password, 
    needs_rehash,
    create_access_token, 
    decode_access_token
)
from src.core.auth import get_current_user_email, security
from src.modules.vehicle_hub.database import SessionLocal, engine, Base
from src.modules.vehicle_hub.models import Customer, Vehicle as VehicleModel, ServiceRecord as ServiceRecordModel, CustomerCommand
# decode_vin_api není již používán - VIN decode endpoint je v decoder routeru
# Vehicle Decoder Engine router
try:
    from src.modules.vehicle_hub.decoder.router import router as decoder_router
    DECODER_AVAILABLE = True
except ImportError as e:
    print(f"[SERVER] Warning: Vehicle Decoder Engine není dostupný: {e}")
    DECODER_AVAILABLE = False

# Vytvoření tabulek
Base.metadata.create_all(bind=engine)

# BEZPEČNOST: Kontrola JWT_SECRET_KEY v produkci
if ENVIRONMENT == "production":
    default_secret = "toozhub2-dev-secret-key-change-in-production"
    if JWT_SECRET_KEY == default_secret:
        import sys
        print("[SERVER] ERROR: KRITICKA CHYBA BEZPECNOSTI!")
        print("[SERVER] V produkci musí být nastaven JWT_SECRET_KEY v .env souboru!")
        print("[SERVER] Výchozí hodnota není bezpečná.")
        print("[SERVER] Vygenerujte nový klíč pomocí: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        sys.exit(1)
    else:
        print("[SERVER] OK: JWT_SECRET_KEY je nastaven (neni vychozi hodnota)")

# Import version info
try:
    from VERSION import __version__, __version_name__, __build_date__, __update_info__
    APP_VERSION = __version__
    APP_VERSION_NAME = __version_name__
    BUILD_DATE = __build_date__
    UPDATE_INFO = __update_info__
except ImportError:
    # Fallback pokud VERSION.py neexistuje
    APP_VERSION = "2.1.0"
    APP_VERSION_NAME = "TOOZHUB2.1"
    BUILD_DATE = "2025-01-27"
    UPDATE_INFO = "Aktualizace s vizuálními úpravami a vylepšeními"

app = FastAPI(title="TooZ Hub 2 API", version=APP_VERSION)

# =============================================================================
# GLOBÁLNÍ EXCEPTION HANDLER - ZABRÁNÍ PÁDŮM SERVERU
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Globální handler pro všechny neošetřené výjimky.
    Zabraňuje pádu serveru a vrací chybovou odpověď.
    """
    import traceback
    
    # Logovat chybu
    error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(f"[ERROR] Neošetřená výjimka: {type(exc).__name__}: {str(exc)}")
    print(f"[ERROR] Path: {request.url.path}")
    print(f"[ERROR] Method: {request.method}")
    print(f"[ERROR] Traceback:\n{error_traceback}")
    
    # Vrátit chybovou odpověď (nechat server běžet)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Interní chyba serveru: {str(exc)}",
            "type": type(exc).__name__,
            "path": request.url.path
        }
    )

# Security - použít z src.core.auth (definováno tam)

# Security Middleware - přidat před CORS
from src.core.security_middleware import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    AntiTamperingMiddleware
)
from src.core.rate_limiter import rate_limiter  # Globální instance pro rate limiting

# Security headers (nejdřív - aplikuje se na všechny odpovědi)
app.add_middleware(SecurityHeadersMiddleware)

# Anti-tampering (detekce manipulace)
app.add_middleware(AntiTamperingMiddleware)

# Rate limiting (ochrana proti DDoS)
app.add_middleware(RateLimitMiddleware, calls=100, period=60)

# CORS middleware - dynamicky podle prostředí (produkce vs development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Dynamicky z config.py (omezené v produkci, všechny v dev)
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

# Include API v1 routery (TooZ Hub v1.0)
try:
    from src.modules.vehicle_hub.routers_v1 import api_router as v1_api_router
    app.include_router(v1_api_router)
    print("[SERVER] API v1 routery zaregistrovány: /api/v1/")
except ImportError as e:
    print(f"[SERVER] Warning: API v1 routery nejsou dostupné: {e}")

# Include Autopilot M2M API router
try:
    from src.modules.vehicle_hub.routers_v1.autopilot import router as autopilot_router
    app.include_router(autopilot_router)
    print("[SERVER] Autopilot M2M API router zaregistrován: /api/autopilot/")
except ImportError as e:
    print(f"[SERVER] Warning: Autopilot M2M API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

# Include Customer Commands API router (Command Bot v1)
try:
    from src.modules.vehicle_hub.routers_v1.customer_commands import router as customer_commands_router
    app.include_router(customer_commands_router)
    print("[SERVER] Customer Commands API router zaregistrován: /api/customer-commands/")
except ImportError as e:
    print(f"[SERVER] Warning: Customer Commands API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

# Include Admin API router
try:
    from src.server.admin_api import router as admin_api_router
    app.include_router(admin_api_router)
    print("[SERVER] Admin API router zaregistrován: /admin-api/")
except ImportError as e:
    print(f"[SERVER] Warning: Admin API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

# Include Instances API router (multi-tenant)
try:
    from src.server.routers import instances
    app.include_router(instances.router)
    print("[SERVER] Instances API router zaregistrován: /api/instances/")
except ImportError as e:
    print(f"[SERVER] Warning: Instances API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

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
    """Kompletní informace o uživateli"""
    id: int
    email: str
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: bool = True
    notify_sms: bool = False
    notify_stk: bool = True
    notify_oil: bool = True
    notify_general: bool = True
    role: str = "user"
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Model pro aktualizaci uživatelského profilu"""
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_stk: Optional[bool] = None
    notify_oil: Optional[bool] = None
    notify_general: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    """Model pro změnu hesla"""
    current_password: str
    new_password: str


# Schémata pro vehicles, service records, reservations jsou nyní v src/modules/vehicle_hub/routers_v1/schemas.py
# (VehicleCreateV1, VehicleOutV1, ServiceRecordCreateV1, ServiceRecordOutV1, ReservationCreateV1, ReservationOutV1)
# VIN decode schémata jsou v src/modules/vehicle_hub/decoder/models.py
# Reminder schémata jsou v src/modules/vehicle_hub/routers_v1/schemas.py
# (ReminderOutV1, ReminderCreateV1, ReminderUpdateV1)


# ============= POMOCNÉ FUNKCE =============

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()




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
    
    # Získat default tenant_id (pro single-tenant instalace)
    from src.modules.vehicle_hub.models import Tenant
    default_tenant = db.query(Tenant).first()
    if not default_tenant:
        # Vytvořit default tenant, pokud neexistuje
        default_tenant = Tenant(name="Default Tenant", license_key="default-license")
        db.add(default_tenant)
        db.commit()
        db.refresh(default_tenant)
    
    customer = Customer(
        tenant_id=default_tenant.id,  # Nastavit tenant_id
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
            "ico": customer.ico,
            "role": customer.role or "user"
        }
    )


@app.post("/user/login", response_model=TokenResponse)
def login_user(login_data: UserLogin, request: Request, db=Depends(get_db)):
    """
    Přihlášení uživatele
    Rate limiting je řešen přes RateLimitMiddleware (globální) a specifický limit pro tento endpoint
    """
    try:
        # Rate limiting kontrolu provádí middleware, ale můžeme přidat dodatečnou kontrolu
        # pro specifický endpoint pomocí IP adresy
        client_ip = request.client.host if request.client else "unknown"
        key = f"login:{client_ip}"
        
        # Kontrola rate limitu (5 pokusů za minutu)
        if not rate_limiter.check_rate_limit(key, max_calls=5, period=60):
            raise HTTPException(
                status_code=429,
                detail="Příliš mnoho pokusů o přihlášení. Zkuste to znovu za minutu."
            )
        
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
                "ico": customer.ico,
                "role": customer.role or "user"
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions (401, 429, etc.)
        raise
    except Exception as e:
        # Logovat všechny ostatní chyby
        import traceback
        error_details = traceback.format_exc()
        print(f"[LOGIN ERROR] {str(e)}")
        print(f"[LOGIN ERROR] Traceback:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Interní chyba serveru: {str(e)}"
        )


@app.get("/user/me", response_model=UserResponse)
def get_current_user(email: str = Depends(get_current_user_email), db=Depends(get_db)):
    """Vrátí aktuálně přihlášeného uživatele"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return customer


@app.put("/user/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Aktualizuje profil přihlášeného uživatele"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    
    # Aktualizovat pouze poskytnutá pole
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(customer, field):
            setattr(customer, field, value)
    
    db.commit()
    db.refresh(customer)
    return customer


@app.put("/user/change-password")
def change_password(
    password_data: ChangePasswordRequest,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Změní heslo přihlášeného uživatele a pošle potvrzovací email"""
    from src.modules.email_client.service import EmailService
    from datetime import datetime
    
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    
    # Ověřit současné heslo
    if not customer.password_hash:
        raise HTTPException(status_code=400, detail="Uživatel nemá nastavené heslo")
    
    if not verify_password(password_data.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")
    
    # Validace nového hesla
    if not password_data.new_password or len(password_data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nové heslo musí mít alespoň 6 znaků")
    
    # Nastavit nové heslo
    customer.password_hash = hash_password(password_data.new_password)
    db.commit()
    
    # Odeslat potvrzovací email
    email_sent = False
    email_error = None
    email_service = EmailService()
    
    try:
        if email_service.is_configured():
            print(f"[CHANGE_PASSWORD] Odesílám potvrzovací email na: {email}")
            
            # Získat jméno uživatele pro personalizaci emailu
            user_name = customer.name or "Uživateli"
            change_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
            
            email_body = f"""
Dobrý den {user_name},

vaše heslo k účtu v TooZ Hub 2 bylo úspěšně změněno.

Změna byla provedena: {change_time} UTC

Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu.

S pozdravem,
TooZ Hub 2
"""
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Potvrzení změny hesla - TooZ Hub 2</h2>
        <p>Dobrý den {user_name},</p>
        <p>vaše heslo k účtu v <strong>TooZ Hub 2</strong> bylo úspěšně změněno.</p>
        <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Datum změny:</strong> {change_time} UTC</p>
        </div>
        <p style="color: #ef4444; font-weight: bold;">Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 0.9em;">S pozdravem,<br>TooZ Hub 2</p>
    </div>
</body>
</html>
"""
            try:
                email_service.send_simple_email(
                    to=email,
                    subject="Potvrzení změny hesla - TooZ Hub 2",
                    body=email_body,
                    html_body=html_body
                )
                email_sent = True
                print(f"[CHANGE_PASSWORD] OK: Potvrzovací email úspěšně odeslán na: {email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[CHANGE_PASSWORD] ERROR: Chyba při odesílání emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[CHANGE_PASSWORD] WARNING: Email není nakonfigurován (chybí SMTP údaje)")
    except Exception as e:
        email_error = str(e)
        print(f"[CHANGE_PASSWORD] ERROR: Neočekávaná chyba: {email_error}")
        import traceback
        traceback.print_exc()
    
    # Vrátit odpověď s informací o odeslání emailu
    response_message = "Heslo bylo úspěšně změněno"
    if email_sent:
        response_message += " a potvrzovací email byl odeslán"
    elif email_error:
        response_message += f" (email nebyl odeslán: {email_error})"
    else:
        response_message += " (email není nakonfigurován)"
    
    return {
        "message": response_message,
        "email_sent": email_sent,
        "password_changed": True
    }


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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@app.post("/user/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db=Depends(get_db)):
    """Odeslání reset odkazu na email"""
    from datetime import timedelta
    import secrets
    from src.modules.email_client.service import EmailService
    from src.core.config import PUBLIC_API_BASE_URL
    
    customer = db.query(Customer).filter(Customer.email == request.email).first()
    
    # Vždy vrátit úspěch (bezpečnost - neodhalit, zda email existuje)
    if not customer:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz"}
    
    # Vytvořit reset token
    reset_token = secrets.token_urlsafe(32)
    reset_token_expires = datetime.utcnow() + timedelta(hours=24)  # 24 hodin platnost
    
    customer.reset_token = reset_token
    customer.reset_token_expires = reset_token_expires
    db.commit()
    
    # Vytvořit reset odkaz
    reset_url = f"{PUBLIC_API_BASE_URL}/reset-password.html?token={reset_token}"
    
    # Odeslat email
    email_sent = False
    email_error = None
    email_service = EmailService()  # Definovat před try blokem
    
    try:
        # Diagnostika - zkontrolovat konfiguraci
        print(f"[RESET] Kontroluji email konfiguraci...")
        print(f"[RESET] SMTP_HOST: {email_service.host}")
        print(f"[RESET] SMTP_PORT: {email_service.port}")
        print(f"[RESET] SMTP_USER: {'***' if email_service.username else '(není nastaveno)'}")
        print(f"[RESET] SMTP_FROM: {email_service.from_email}")
        print(f"[RESET] is_configured(): {email_service.is_configured()}")
        
        if email_service.is_configured():
            print(f"[RESET] Pokusím se odeslat email na: {request.email}")
            email_body = f"""
Dobrý den,

obdrželi jsme žádost o obnovení hesla k vašemu účtu v TooZ Hub 2.

Pro vytvoření nového hesla klikněte na následující odkaz:
{reset_url}

Tento odkaz je platný 24 hodin.

Pokud jste tento požadavek nevytvořili, ignorujte tento email.

S pozdravem,
TooZ Hub 2
"""
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Obnovení hesla - TooZ Hub 2</h2>
        <p>Dobrý den,</p>
        <p>obdrželi jsme žádost o obnovení hesla k vašemu účtu.</p>
        <p>Pro vytvoření nového hesla klikněte na následující tlačítko:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background-color: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Obnovit heslo</a>
        </div>
        <p>Nebo zkopírujte tento odkaz do prohlížeče:</p>
        <p style="word-break: break-all; color: #6366f1;">{reset_url}</p>
        <p><small>Tento odkaz je platný 24 hodin.</small></p>
        <p>Pokud jste tento požadavek nevytvořili, ignorujte tento email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 0.9em;">S pozdravem,<br>TooZ Hub 2</p>
    </div>
</body>
</html>
"""
            try:
                email_service.send_simple_email(
                    to=request.email,
                    subject="Obnovení hesla - TooZ Hub 2",
                    body=email_body,
                    html_body=html_body
                )
                email_sent = True
                print(f"[RESET] OK: Email uspesne odeslan na: {request.email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[RESET] ERROR: Chyba pri odesilani emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[RESET] WARNING: Email NENI nakonfigurovan (chybi SMTP udaje)")
            print(f"[RESET] Reset URL (pro testování): {reset_url}")
            print(f"[RESET] Nastavte v .env souboru: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")
    except Exception as e:
        email_error = str(e)
        print(f"[RESET] ERROR: Neocekavana chyba: {email_error}")
        import traceback
        traceback.print_exc()
    
    # Vrátit odpověď s informací o stavu
    if email_sent:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz", "email_sent": True}
    elif email_error:
        is_configured = email_service.is_configured() if email_service else False
        # Zkontrolovat, zda je chyba autentizace
        error_message = "Email nebyl odeslán."
        if "authentication failed" in email_error.lower() or "535" in email_error:
            error_message = "Chyba autentizace SMTP - zkontrolujte uživatelské jméno a heslo v .env souboru."
        elif "connection" in email_error.lower() or "timeout" in email_error.lower():
            error_message = "Chyba připojení k SMTP serveru - zkontrolujte SMTP_HOST a SMTP_PORT."
        else:
            error_message = f"Email nebyl odeslán: {email_error}"
        
        return {
            "message": error_message,
            "email_sent": False,
            "error": email_error,
            "reset_url": reset_url,  # Vždy vrátit URL pro testování při chybě
            "error_detail": email_error  # Detailní chyba pro debug
        }
    else:
        return {
            "message": "Email není nakonfigurován. Nastavte SMTP údaje v .env souboru.",
            "email_sent": False,
            "reset_url": reset_url  # Vrátit URL pro testování
        }


@app.get("/reset-password.html", response_class=HTMLResponse)
def reset_password_page():
    """Servuje reset-password.html stránku"""
    web_path = Path(__file__).parent.parent.parent / "web" / "reset-password.html"
    if web_path.exists():
        return FileResponse(web_path)
    else:
        raise HTTPException(status_code=404, detail="Reset password page not found")


@app.post("/user/reset-password")
def reset_password(request: ResetPasswordRequest, db=Depends(get_db)):
    """Reset hesla pomocí tokenu"""
    # Validace hesla
    if not request.new_password or len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    
    # Najít uživatele podle tokenu
    customer = db.query(Customer).filter(
        Customer.reset_token == request.token,
        Customer.reset_token_expires > datetime.utcnow()
    ).first()
    
    if not customer:
        raise HTTPException(status_code=400, detail="Neplatný nebo expirovaný reset token")
    
    # Nastavit nové heslo
    customer.password_hash = hash_password(request.new_password)
    customer.reset_token = None
    customer.reset_token_expires = None
    db.commit()
    
    return {"message": "Heslo bylo úspěšně změněno"}


# ============= VOZIDLA ENDPOINTY =============
# Endpointy pro vehicles jsou nyní v src/modules/vehicle_hub/routers_v1/vehicles.py
# Router je zaregistrován pod /api/v1/vehicles
# VIN decode endpoint je v src/modules/vehicle_hub/decoder/router.py pod /api/vehicles/decode-vin

# ============= SERVISNÍ ZÁZNAMY ENDPOINTY =============
# Endpointy pro service records jsou nyní v src/modules/vehicle_hub/routers_v1/service_records.py
# Router je zaregistrován pod /api/v1/vehicles/{vehicle_id}/records

# ============= SERVISY =============
# Endpointy pro services jsou nyní v src/modules/vehicle_hub/routers_v1/services.py
# Router je zaregistrován pod /api/v1/services

# ============= REZERVACE =============
# Endpointy pro reservations jsou nyní v src/modules/vehicle_hub/routers_v1/reservations.py
# Router je zaregistrován pod /api/v1/reservations


# ============= PŘIPOMÍNKY =============
# Endpointy pro reminders jsou nyní v src/modules/vehicle_hub/routers_v1/reminders.py
# Router je zaregistrován pod /api/v1/reminders


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

# Mount admin static files (jako statické soubory, podobně jako /web)
try:
    admin_web_path = Path(__file__).parent.parent.parent / "web_admin"
    if admin_web_path.exists():
        app.mount("/web_admin", StaticFiles(directory=str(admin_web_path), html=True), name="web_admin")
        print(f"[SERVER] Admin web zaregistrován: /web_admin/ (directory: {admin_web_path})")
        # Zachovat /admin-static pro zpětnou kompatibilitu (CSS/JS soubory)
        app.mount("/admin-static", StaticFiles(directory=str(admin_web_path)), name="admin_static")
        print(f"[SERVER] Admin static files zaregistrovány: /admin-static/ (directory: {admin_web_path})")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount admin web directory: {e}")


# ============= ROOT & HEALTH =============

@app.get("/")
def root():
    """Root endpoint"""
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    return {
        "message": "TooZ Hub 2 API",
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
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
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    return {
        "status": "ok",
        "project": "TOOZHUB2",
        "service": "TooZ Hub 2 API",
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
        "updated": True  # Indikátor, že proběhla aktualizace
    }


@app.get("/version")
def get_version():
    """Endpoint pro získání informací o verzi projektu"""
    try:
        from src.server.version import get_version_info
        return get_version_info()
    except Exception as e:
        # Fallback na VERSION.py
        try:
            from VERSION import __version__, __version_name__
            from datetime import datetime
            return {
                "project": "TooZ Hub 2",
                "version": __version__,
                "build_time": datetime.now().isoformat()
            }
        except ImportError:
            return {
                "project": "TooZ Hub 2",
                "version": APP_VERSION,
                "build_time": datetime.now().isoformat()
            }


@app.get("/version/history")
def get_version_history(db=Depends(get_db)):
    """Endpoint pro získání historie verzí"""
    try:
        from src.modules.vehicle_hub.models import VersionHistory
        
        # Načtení všech záznamů z historie verzí (nejnovější první)
        history = db.query(VersionHistory).order_by(VersionHistory.applied_at.desc()).all()
        
        return {
            "history": [
                {
                    "id": entry.id,
                    "version": entry.version,
                    "description": entry.description,
                    "applied_at": entry.applied_at.isoformat() if entry.applied_at else None
                }
                for entry in history
            ],
            "total": len(history)
        }
    except Exception as e:
        # Pokud tabulka ještě neexistuje, vrať prázdnou historii
        print(f"[VERSION] Warning: Nelze načíst historii verzí: {e}")
        return {
            "history": [],
            "total": 0,
            "error": "Historie verzí není dostupná"
        }


# Inicializace historie verzí při startu serveru
def init_version_history():
    """Inicializuje historii verzí - zapíše aktuální verzi, pokud tam není"""
    try:
        from src.server.version import read_version, log_version_update
        
        db = SessionLocal()
        try:
            # Načtení aktuální verze
            current_version = read_version()
            
            # Kontrola, zda už verze není v historii
            existing = db.query(VersionHistory).filter(VersionHistory.version == current_version).first()
            if not existing:
                # Zapsání verze do historie
                log_version_update(
                    db=db,
                    version=current_version,
                    description="Kompletní redesign UI + zavedení verzování"
                )
                print(f"[SERVER] ✅ Verze {current_version} zapsána do historie verzí")
            else:
                print(f"[SERVER] ℹ️  Verze {current_version} už je v historii verzí")
        finally:
            db.close()
    except Exception as e:
        print(f"[SERVER] Warning: Nelze inicializovat historii verzí: {e}")
        import traceback
        traceback.print_exc()

# Spustit inicializaci historie verzí
try:
    init_version_history()
except Exception as e:
    print(f"[SERVER] Warning: Chyba při inicializaci historie verzí: {e}")

if __name__ == "__main__":
    import uvicorn
    
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    print("=" * 60)
    print(f"[SERVER] 🚀 TooZ Hub 2 API Server")
    print(f"[SERVER] 📦 Verze: {version} ({version_name})")
    print(f"[SERVER] 📅 Datum buildu: {build_date}")
    print(f"[SERVER] 🔄 Aktualizace: {update_info}")
    print("=" * 60)
    print(f"[SERVER] Spouštím server na {HOST}:{PORT}")
    print(f"[SERVER] Režim: {ENVIRONMENT}")
    print(f"[SERVER] CORS origins: {ALLOWED_ORIGINS}")
    print("")
    
    uvicorn.run(app, host=HOST, port=PORT)
