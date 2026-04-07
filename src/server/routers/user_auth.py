from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func

from src.core.config import ENVIRONMENT, PUBLIC_API_BASE_URL
from src.core.branding import APP_DISPLAY_NAME
from src.core.rate_limiter import rate_limiter
from src.core.security import create_access_token, hash_password, needs_rehash, verify_password
from src.modules.email_client.templates import build_app_url, render_email_layout, render_panel
from src.modules.vehicle_hub.account_state import (
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    touch_customer_last_login,
)
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings, ServiceRegistrationRequest
from src.modules.vehicle_hub.routers_v1.auth import get_current_user as get_v1_current_user
from src.modules.vehicle_hub.routers_v1.ares_lookup import lookup_ares as lookup_ares_v1
from src.modules.vehicle_hub.tenant_provisioning import create_dedicated_tenant, ensure_default_license_for_tenant
from src.server.main_helpers import (
    ForgotPasswordRequest,
    LoginResponse,
    RegisterTokenResponse,
    ResetPasswordRequest,
    ServiceRegisterRequest,
    ServiceRegisterResponse,
    TokenResponse,
    TwoFactorLoginVerifyRequest,
    UserLogin,
    UserRegister,
    get_active_ip_block,
    get_customer_by_email,
    normalize_email,
    normalize_ico,
    send_registration_alert_email,
)
from src.server.security_helpers import (
    create_2fa_login_challenge,
    get_2fa_login_challenge,
    pop_2fa_login_challenge,
    set_2fa_login_challenge,
    verify_totp,
)
from src.server.security_tracking import extract_client_ip, log_security_event


router = APIRouter()


@router.post("/user/register", response_model=RegisterTokenResponse)
def register_user(user_data: UserRegister, db=Depends(get_db)):
    normalized_email = normalize_email(user_data.email)
    normalized_ico = normalize_ico(user_data.ico)

    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")

    existing = get_customer_by_email(db, normalized_email)
    if existing:
        raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")

    try:
        hashed_password = hash_password(user_data.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dedicated_tenant = create_dedicated_tenant(
        db,
        owner_email=normalized_email,
        owner_name=user_data.name,
    )

    customer = Customer(
        tenant_id=dedicated_tenant.id,
        email=normalized_email,
        password_hash=hashed_password,
        name=user_data.name,
        ico=normalized_ico,
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

    ensure_default_license_for_tenant(db, dedicated_tenant.id)

    email_sent = False
    registration_email_status = "not_configured"
    try:
        from src.modules.email_client.service import EmailService

        email_service = EmailService()
        if email_service.is_configured():
            registered_at = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
            user_name = (customer.name or "uživateli").strip()

            email_body = f"""
Dobrý den {user_name},

vaše registrace do aplikace {APP_DISPLAY_NAME} byla úspěšně dokončena.

Registrovaný účet: {customer.email}
Datum registrace: {registered_at} UTC

Nyní se můžete přihlásit a začít spravovat svá vozidla.

S pozdravem,
{APP_DISPLAY_NAME}
"""

            html_body = render_email_layout(
                title="Účet je připraven",
                subtitle="Registrace byla úspěšně dokončena.",
                intro=f"Dobrý den {user_name},",
                paragraphs=[
                    f"vaše registrace do aplikace {APP_DISPLAY_NAME} byla úspěšně dokončena.",
                    "Teď se můžete přihlásit a začít spravovat svá vozidla, servisní historii i připomínky.",
                ],
                panels=[
                    render_panel(
                        title="Přehled účtu",
                        rows=[
                            ("Registrovaný účet", customer.email),
                            ("Datum registrace", f"{registered_at} UTC"),
                        ],
                    )
                ],
                cta_label="Otevřít aplikaci",
                cta_url=build_app_url(),
                accent="#f59e0b",
            )
            try:
                email_service.send_simple_email(
                    to=customer.email,
                    subject=f"Potvrzení registrace - {APP_DISPLAY_NAME}",
                    body=email_body,
                    html_body=html_body,
                )
                email_sent = True
                registration_email_status = "sent"
                print(f"[REGISTER] OK: Potvrzovací email odeslán na: {customer.email}")
            except Exception as email_ex:
                registration_email_status = "failed"
                print(f"[REGISTER] ERROR: Nepodařilo se odeslat registrační email: {email_ex}")
        else:
            print("[REGISTER] WARNING: SMTP není nakonfigurováno, potvrzovací email nebyl odeslán")
    except Exception as exc:
        registration_email_status = "failed"
        print(f"[REGISTER] ERROR: Neočekávaná chyba při odesílání registračního emailu: {exc}")

    developer_alert = send_registration_alert_email(
        db,
        registration_type="user",
        account_email=customer.email,
        account_name=customer.name,
        account_ico=customer.ico,
        metadata={
            "customer_id": customer.id,
            "tenant_id": customer.tenant_id,
            "role": customer.role or "user",
        },
    )
    if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
        print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

    access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

    return RegisterTokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
        },
        email_sent=email_sent,
        registration_email_status=registration_email_status,
    )


@router.post("/user/register/service-request", response_model=ServiceRegisterResponse)
def register_service_request(payload: ServiceRegisterRequest, db=Depends(get_db)):
    normalized_email = normalize_email(payload.email)
    ico_digits = normalize_ico(payload.ico) or ""

    if not payload.password or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    if len(ico_digits) != 8:
        raise HTTPException(status_code=400, detail="IČO musí obsahovat přesně 8 číslic")

    if get_customer_by_email(db, normalized_email):
        raise HTTPException(status_code=400, detail="Účet s tímto emailem již existuje")

    existing_service_customer_same_ico = (
        db.query(Customer)
        .filter(
            Customer.role == "service",
            Customer.ico == ico_digits,
            func.lower(Customer.email) != normalized_email,
        )
        .first()
    )
    if existing_service_customer_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO je už registrováno u jiného servisního účtu.",
        )

    existing_request_same_ico = (
        db.query(ServiceRegistrationRequest)
        .filter(
            ServiceRegistrationRequest.ico == ico_digits,
            func.lower(ServiceRegistrationRequest.email) != normalized_email,
            ServiceRegistrationRequest.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing_request_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO už má aktivní nebo schválenou servisní registraci.",
        )

    existing_request = (
        db.query(ServiceRegistrationRequest)
        .filter(func.lower(ServiceRegistrationRequest.email) == normalized_email)
        .first()
    )

    hashed_password = hash_password(payload.password)
    now = datetime.utcnow()

    if existing_request:
        if existing_request.status == "pending":
            raise HTTPException(
                status_code=400,
                detail="Žádost pro tento email už čeká na schválení developerem.",
            )
        if existing_request.status == "approved":
            raise HTTPException(
                status_code=400,
                detail="Tato servisní registrace už byla schválena. Přihlaste se.",
            )

        existing_request.status = "pending"
        existing_request.password_hash = hashed_password
        existing_request.ico = ico_digits
        existing_request.service_name = payload.service_name.strip()
        existing_request.responsible_person = payload.responsible_person.strip()
        existing_request.phone = payload.phone.strip()
        existing_request.street = payload.street.strip()
        existing_request.street_number = (payload.street_number or "").strip() or None
        existing_request.city = payload.city.strip()
        existing_request.zip = payload.zip.strip()
        existing_request.dic = (payload.dic or "").strip() or None
        existing_request.registration_purpose = payload.registration_purpose.strip()
        existing_request.reviewed_by_customer_id = None
        existing_request.reviewed_at = None
        existing_request.review_note = None
        existing_request.approved_customer_id = None
        existing_request.approved_tenant_id = None
        existing_request.updated_at = now
        db.commit()
        db.refresh(existing_request)

        developer_alert = send_registration_alert_email(
            db,
            registration_type="service",
            account_email=existing_request.email,
            account_name=existing_request.service_name,
            account_ico=existing_request.ico,
            metadata={
                "request_id": existing_request.id,
                "status": existing_request.status,
                "city": existing_request.city,
                "responsible_person": existing_request.responsible_person,
                "phone": existing_request.phone,
                "purpose": existing_request.registration_purpose[:180],
                "event": "service_request_resubmitted",
            },
        )
        if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
            print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

        return ServiceRegisterResponse(
            request_id=existing_request.id,
            status="pending",
            message="Žádost o servisní registraci byla znovu odeslána ke schválení.",
        )

    new_request = ServiceRegistrationRequest(
        status="pending",
        email=normalized_email,
        password_hash=hashed_password,
        ico=ico_digits,
        service_name=payload.service_name.strip(),
        responsible_person=payload.responsible_person.strip(),
        phone=payload.phone.strip(),
        street=payload.street.strip(),
        street_number=(payload.street_number or "").strip() or None,
        city=payload.city.strip(),
        zip=payload.zip.strip(),
        dic=(payload.dic or "").strip() or None,
        registration_purpose=payload.registration_purpose.strip(),
        created_at=now,
        updated_at=now,
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    developer_alert = send_registration_alert_email(
        db,
        registration_type="service",
        account_email=new_request.email,
        account_name=new_request.service_name,
        account_ico=new_request.ico,
        metadata={
            "request_id": new_request.id,
            "status": new_request.status,
            "city": new_request.city,
            "responsible_person": new_request.responsible_person,
            "phone": new_request.phone,
            "purpose": new_request.registration_purpose[:180],
            "event": "service_request_created",
        },
    )
    if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
        print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

    return ServiceRegisterResponse(
        request_id=new_request.id,
        status="pending",
        message="Žádost o servisní účet byla přijata. Aktivace proběhne po ověření developerem.",
    )


@router.post("/user/login", response_model=LoginResponse)
def login_user(login_data: UserLogin, request: Request, db=Depends(get_db)):
    normalized_email = normalize_email(login_data.email)
    masked = normalized_email[:2] + "***" + normalized_email[-1:] if len(normalized_email) > 3 else "***"
    print(f"[LOGIN] Request received for {masked} (path={request.url.path})")
    try:
        client_ip = extract_client_ip(request) or "unknown"
        ip_block = get_active_ip_block(db, client_ip)
        if ip_block:
            detail_payload = {
                "reason": "blocked_ip",
                "blocked_at": ip_block.blocked_at.isoformat() if ip_block.blocked_at else None,
                "expires_at": ip_block.expires_at.isoformat() if ip_block.expires_at else None,
            }
            if ip_block.reason:
                detail_payload["block_reason"] = ip_block.reason
            log_security_event(
                event_type="login_blocked_ip",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details=detail_payload,
            )
            raise HTTPException(
                status_code=403,
                detail="Přístup z této IP adresy je dočasně zablokován.",
            )

        key = f"login:{normalized_email}:{client_ip}"
        if not rate_limiter.check_rate_limit(key, max_calls=5, period=60):
            log_security_event(
                event_type="login_rate_limited",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "rate_limit", "max_calls": 5, "period_sec": 60},
            )
            raise HTTPException(
                status_code=429,
                detail="Příliš mnoho pokusů o přihlášení. Zkuste to znovu za minutu.",
            )

        customer = get_customer_by_email(db, normalized_email)
        if not customer:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "user_not_found"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        if customer_is_deleted(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_deleted"},
            )
            raise HTTPException(status_code=403, detail="Účet byl deaktivován.")

        if customer_is_disabled(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_disabled"},
            )
            raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")

        if not customer.password_hash:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "missing_password_hash"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        if not verify_password(login_data.password, customer.password_hash):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "invalid_password"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        requested_role = (login_data.expected_role or "").strip().lower()
        if requested_role in {"user", "service"}:
            customer_role = (customer.role or "user").strip().lower()
            if requested_role == "service" and customer_role not in {"service", "admin", "developer_admin"}:
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_service", "customer_role": customer_role},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet není servisní. Přepněte režim na Uživatel.",
                )
            if requested_role == "user" and customer_role == "service":
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_user", "customer_role": customer_role},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet je servisní. Přepněte režim na Servis.",
                )

        if needs_rehash(customer.password_hash):
            customer.password_hash = hash_password(login_data.password)
            db.commit()

        security_settings = (
            db.query(CustomerSecuritySettings)
            .filter(CustomerSecuritySettings.customer_id == customer.id)
            .first()
        )
        if security_settings and security_settings.two_factor_enabled and security_settings.totp_secret:
            challenge_token, expires_in = create_2fa_login_challenge(
                customer=customer,
                expected_role=requested_role if requested_role in {"user", "service"} else None,
            )
            log_security_event(
                event_type="login_2fa_challenge_issued",
                request=request,
                user_email=customer.email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"role": customer.role or "user", "expires_in_sec": expires_in},
            )
            return LoginResponse(
                two_factor_required=True,
                challenge_token=challenge_token,
                challenge_expires_in=expires_in,
            )

        touch_customer_last_login(customer)
        db.commit()
        access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

        log_security_event(
            event_type="login_success",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"role": customer.role or "user"},
        )

        return LoginResponse(
            access_token=access_token,
            user={
                "id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "ico": customer.ico,
                "role": customer.role or "user",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        import traceback

        error_details = traceback.format_exc()
        print(f"[LOGIN ERROR] {str(exc)}")
        print(f"[LOGIN ERROR] Traceback:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Interní chyba serveru: {str(exc)}",
        ) from exc


@router.post("/user/login/2fa", response_model=TokenResponse)
def verify_login_two_factor(
    payload: TwoFactorLoginVerifyRequest,
    request: Request,
    db=Depends(get_db),
):
    challenge = get_2fa_login_challenge(payload.challenge_token)
    if not challenge:
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela nebo je neplatná. Přihlaste se znovu.",
        )

    expires_at = float(challenge.get("expires_at", 0))
    if expires_at <= time.time():
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela. Přihlaste se znovu.",
        )

    attempts = int(challenge.get("attempts", 0))
    if attempts >= 5:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(
            status_code=429,
            detail="Překročen počet pokusů o 2FA ověření. Přihlaste se znovu.",
        )

    email = challenge.get("email")
    customer = get_customer_by_email(db, str(email or ""))
    if not customer:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=401, detail="Uživatel pro 2FA ověření nebyl nalezen")
    if customer_is_deleted(customer):
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Účet byl deaktivován.")
    if customer_is_disabled(customer):
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")

    expected_role = str(challenge.get("expected_role") or "").strip().lower()
    customer_role = (customer.role or "user").strip().lower()
    if expected_role == "service" and customer_role not in {"service", "admin", "developer_admin"}:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Tento účet není servisní.")
    if expected_role == "user" and customer_role == "service":
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Tento účet je servisní.")

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if not security_settings or not security_settings.two_factor_enabled or not security_settings.totp_secret:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=400, detail="2FA není pro tento účet aktivní")

    if not verify_totp(security_settings.totp_secret, payload.code):
        challenge["attempts"] = attempts + 1
        set_2fa_login_challenge(payload.challenge_token, challenge)
        log_security_event(
            event_type="login_2fa_failed",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"attempts": challenge["attempts"]},
        )
        raise HTTPException(status_code=401, detail="Neplatný 2FA kód")

    pop_2fa_login_challenge(payload.challenge_token)
    touch_customer_last_login(customer)
    db.commit()
    access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

    log_security_event(
        event_type="login_2fa_success",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return TokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
        },
    )


@router.get("/user/ares")
def get_ares_data(
    ico: str,
    current_user: Customer = Depends(get_v1_current_user),
    db=Depends(get_db),
):
    """Deprecated wrapper. Source-of-truth je /api/v1/ares/{ico}."""
    return lookup_ares_v1(ico=ico, current_user=current_user, db=db)


@router.post("/user/forgot-password")
@router.post("/user/request-password-reset")
def forgot_password(payload: ForgotPasswordRequest, db=Depends(get_db)):
    from src.modules.email_client.service import EmailService

    normalized_email = normalize_email(payload.email)
    customer = get_customer_by_email(db, normalized_email)

    if not customer:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz"}

    target_email = customer.email
    reset_token = secrets.token_urlsafe(32)
    reset_token_expires = datetime.utcnow() + timedelta(hours=24)

    customer.reset_token = reset_token
    customer.reset_token_expires = reset_token_expires
    db.commit()

    reset_url = f"{PUBLIC_API_BASE_URL}/reset-password.html?token={reset_token}"

    email_sent = False
    email_error = None
    email_service = EmailService()

    try:
        print("[RESET] Kontroluji email konfiguraci...")
        print(f"[RESET] SMTP_HOST: {email_service.host}")
        print(f"[RESET] SMTP_PORT: {email_service.port}")
        print(f"[RESET] SMTP_USER: {'***' if email_service.username else '(není nastaveno)'}")
        print(f"[RESET] SMTP_FROM: {email_service.from_email}")
        print(f"[RESET] SMTP configured: {email_service.is_configured()}")

        if email_service.is_configured():
            print(f"[RESET] Pokusím se odeslat email na: {target_email}")
            email_body = f"""
Dobrý den,

obdrželi jsme žádost o obnovení hesla k vašemu účtu v aplikaci {APP_DISPLAY_NAME}.

Pro vytvoření nového hesla klikněte na následující odkaz:
{reset_url}

Tento odkaz je platný 24 hodin.

Pokud jste tento požadavek nevytvořili, ignorujte tento email.

S pozdravem,
{APP_DISPLAY_NAME}
"""
            html_body = render_email_layout(
                title="Obnovení hesla",
                subtitle="Požadavek na změnu hesla k vašemu účtu.",
                intro="Dobrý den,",
                paragraphs=[
                    f"obdrželi jsme žádost o obnovení hesla k vašemu účtu v aplikaci {APP_DISPLAY_NAME}.",
                    "Odkaz je platný 24 hodin. Pokud jste o změnu hesla nežádali, tento e-mail ignorujte.",
                ],
                panels=[
                    render_panel(
                        title="Bezpečnostní informace",
                        rows=[
                            ("Platnost odkazu", "24 hodin"),
                            ("Účet", target_email),
                        ],
                        accent="#ef4444",
                        tone="#fef2f2",
                    )
                ],
                cta_label="Obnovit heslo",
                cta_url=reset_url,
                accent="#f59e0b",
            )
            try:
                email_service.send_simple_email(
                    to=target_email,
                    subject=f"Obnovení hesla - {APP_DISPLAY_NAME}",
                    body=email_body,
                    html_body=html_body,
                )
                email_sent = True
                print(f"[RESET] OK: Email uspesne odeslan na: {target_email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[RESET] ERROR: Chyba pri odesilani emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print("[RESET] WARNING: Email NENI nakonfigurovan (chybi SMTP udaje)")
            print(f"[RESET] Reset URL (pro testování): {reset_url}")
            print("[RESET] Nastavte v .env souboru: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")
    except Exception as exc:
        email_error = str(exc)
        print(f"[RESET] ERROR: Neocekavana chyba: {email_error}")
        import traceback
        traceback.print_exc()

    if email_sent:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz", "email_sent": True}
    if email_error:
        error_message = "Email nebyl odeslán."
        if "authentication failed" in email_error.lower() or "535" in email_error:
            error_message = "Chyba autentizace SMTP - zkontrolujte uživatelské jméno a heslo v .env souboru."
        elif "connection" in email_error.lower() or "timeout" in email_error.lower():
            error_message = "Chyba připojení k SMTP serveru - zkontrolujte SMTP_HOST a SMTP_PORT."
        else:
            error_message = f"Email nebyl odeslán: {email_error}"

        response = {
            "message": error_message,
            "email_sent": False,
        }
        if ENVIRONMENT != "production":
            response["reset_url"] = reset_url
            response["error_detail"] = email_error
        return response

    response = {
        "message": "Email není nakonfigurován. Nastavte SMTP údaje v .env souboru.",
        "email_sent": False,
    }
    if ENVIRONMENT != "production":
        response["reset_url"] = reset_url
    return response


@router.get("/reset-password.html", response_class=HTMLResponse)
def reset_password_page():
    web_path = Path(__file__).parent.parent.parent.parent / "web" / "reset-password.html"
    if web_path.exists():
        return FileResponse(web_path)
    raise HTTPException(status_code=404, detail="Reset password page not found")


@router.post("/user/reset-password")
def reset_password(payload: ResetPasswordRequest, db=Depends(get_db)):
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")

    customer = db.query(Customer).filter(
        Customer.reset_token == payload.token,
        Customer.reset_token_expires > datetime.utcnow(),
    ).first()
    if not customer:
        raise HTTPException(status_code=400, detail="Neplatný nebo expirovaný reset token")

    customer.password_hash = hash_password(payload.new_password)
    customer.reset_token = None
    customer.reset_token_expires = None
    db.commit()

    return {"message": "Heslo bylo úspěšně změněno"}
