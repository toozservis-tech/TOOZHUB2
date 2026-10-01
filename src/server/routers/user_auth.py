from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import secrets
import hashlib
import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.core.session_revocation import revoke_tokens
from sqlalchemy import func

from src.core.config import ENVIRONMENT, PUBLIC_API_BASE_URL
from src.core.branding import APP_DISPLAY_NAME
from src.core.rate_limiter import rate_limiter
from src.core import mfa
from src.server.security_tracking import extract_client_ip, log_security_event
from src.core.security import create_access_token, hash_password, needs_rehash, verify_password, validate_new_password
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



from src.modules.vehicle_hub.email_verification import EmailVerification, issue_verification, prepare_verification
from src.core.auth import get_current_user_email
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


def _limit_auth(request: Request, action: str, email: str = "", calls: int = 5, period: int = 900):
    # Account and IP budgets are independent, so changing one cannot bypass both.
    ip = request.client.host if request.client else "unknown"
    keys = [(f"{action}:ip:{ip}", calls * 4)]
    if email:
        keys.append((f"{action}:account:{hashlib.sha256(email.encode()).hexdigest()}", calls))
    for key, limit in keys:
        if not rate_limiter.check_rate_limit(key, limit, period):
            raise HTTPException(429, "Příliš mnoho pokusů. Zkuste to později.", headers={"Retry-After": str(period)})


def _validate_password(password: str):
    try:
        validate_new_password(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc



class LogoutRequest(BaseModel):
    logout_ticket: str = Field(max_length=2048)


@router.post("/user/logout", status_code=204)
def logout(data: LogoutRequest | None = Body(default=None), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)), db=Depends(get_db)):
    revoke_tokens(db, [credentials.credentials] if credentials else [], tickets=[data.logout_ticket] if data else [])
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/user/register", response_model=RegisterTokenResponse)
def register_user(user_data: UserRegister, request: Request, db=Depends(get_db)):
    _limit_auth(request, "register", calls=5)
    normalized_email = normalize_email(user_data.email)
    normalized_ico = normalize_ico(user_data.ico)

    _validate_password(user_data.password)

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
    db.flush()
    prepare_verification(db, customer)
    db.commit()
    db.refresh(customer)

    ensure_default_license_for_tenant(db, dedicated_tenant.id)

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

    verification_sent = issue_verification(db, customer)
    registration_email_status = "sent" if verification_sent else "failed"
    email_sent = verification_sent
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
def register_service_request(payload: ServiceRegisterRequest, request: Request, db=Depends(get_db)):
    _limit_auth(request, "register-service", calls=5)
    normalized_email = normalize_email(payload.email)
    ico_digits = normalize_ico(payload.ico) or ""

    _validate_password(payload.password)
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
    _limit_auth(request, "login-global", normalized_email, calls=10, period=300)
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

        security_settings = (
            db.query(CustomerSecuritySettings)
            .filter(CustomerSecuritySettings.customer_id == customer.id)
            .first()
        )
        if security_settings and security_settings.two_factor_enabled:
            mfa.read_secret(security_settings.totp_secret)  # A missing/corrupt factor must never downgrade to password-only.
            challenge_token, expires_in = mfa.create_login_challenge(
                db=db, customer=customer,
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
        claims = {"sub": customer.email, "sv": customer_session_version(customer)}
        db.commit()
        access_token = create_access_token(data=claims)

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
        logger.error("Authentication dependency failed; details suppressed to protect credentials")
        raise HTTPException(
            status_code=500,
            detail="Přihlášení se nepodařilo dokončit. Zkuste to později.",
        ) from exc


@router.post("/user/login/2fa", response_model=TokenResponse)
def verify_login_two_factor(
    payload: TwoFactorLoginVerifyRequest,
    request: Request,
    db=Depends(get_db),
):
    _limit_auth(request, "totp-login-ip", calls=10)
    digest = hashlib.sha256(payload.challenge_token.encode()).hexdigest()
    challenge = db.get(mfa.MFALoginChallenge, digest)
    if not challenge or challenge.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Ověření vypršelo. Přihlaste se znovu.")
    mfa.limit_attempt(db, challenge.customer_id, "totp-login", limit=10)
    challenge = (db.query(mfa.MFALoginChallenge).filter(mfa.MFALoginChallenge.digest == digest)
                 .with_for_update().populate_existing().first())
    if not challenge or challenge.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Ověření vypršelo. Přihlaste se znovu.")
    claimed = (db.query(mfa.MFALoginChallenge).filter(mfa.MFALoginChallenge.digest == digest,
                   mfa.MFALoginChallenge.attempts < 5)
               .update({mfa.MFALoginChallenge.attempts: mfa.MFALoginChallenge.attempts + 1}, synchronize_session='fetch'))
    if claimed != 1:
        raise HTTPException(429, "Překročen počet pokusů. Přihlaste se znovu.")
    customer = db.get(Customer, challenge.customer_id)
    if not customer or customer_is_deleted(customer) or customer_is_disabled(customer) or challenge.session_version != customer_session_version(customer):
        db.delete(challenge); db.commit()
        raise HTTPException(401, "Přihlášení již není platné. Přihlaste se znovu.")
    expected_role = challenge.expected_role
    role = (customer.role or "user").strip().lower()
    if (expected_role == "service" and role not in {"service", "admin", "developer_admin"}) or (expected_role == "user" and role == "service"):
        db.delete(challenge); db.commit()
        raise HTTPException(403, "Zvolený typ účtu nesouhlasí.")
    _limit_auth(request, "totp-login-account", customer.email, calls=5)
    settings = mfa.locked_settings(db, customer)
    if not settings.two_factor_enabled or not settings.totp_secret:
        db.delete(challenge); db.commit()
        raise HTTPException(401, "Nastavení ověření se změnilo. Přihlaste se znovu.")
    if not mfa.consume_code(db, settings, payload.code):
        db.commit()  # Persist the attempt budget across workers / restarts.
        raise HTTPException(401, "Neplatný nebo již použitý kód. Vyčkejte na další kód v autentikátoru.")
    db.delete(challenge)
    touch_customer_last_login(customer)
    claims = mfa.verified_claims(customer)
    db.commit()
    access_token = create_access_token(claims)

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
def forgot_password(payload: ForgotPasswordRequest, request: Request, db=Depends(get_db)):
    from src.modules.email_client.service import EmailService

    normalized_email = normalize_email(payload.email)
    _limit_auth(request, "password-recovery", normalized_email, calls=3)
    email_service = EmailService()
    # Report a global outage identically for every address; never claim delivery.
    if not email_service.is_configured():
        raise HTTPException(503, "Obnova hesla je dočasně nedostupná. Kontaktujte podporu.")
    result = {"message": "Pokud existuje aktivní účet s tímto e-mailem, obdržíte odkaz pro obnovu hesla."}
    customer = get_customer_by_email(db, normalized_email)
    if not customer or customer_is_deleted(customer) or customer_is_disabled(customer):
        return result

    token = secrets.token_urlsafe(32)
    digest = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
    customer.reset_token = digest
    customer.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
    db.commit()
    # Fragment stays out of HTTP access logs and Referer headers.
    reset_url = f"{PUBLIC_API_BASE_URL.rstrip('/')}/reset-password.html#token={token}"
    try:
        email_service.send_simple_email(
            to=customer.email,
            subject=f"Obnovení hesla – {APP_DISPLAY_NAME}",
            body=f"Pro obnovu hesla otevřete {reset_url}\nOdkaz platí 30 minut a lze jej použít jen jednou. Pokud jste o obnovu nežádali, e-mail ignorujte.",
            html_body=render_email_layout(
                title="Obnovení hesla", subtitle="Nové heslo. Bezpečný přístup k vašemu účtu.", intro="Dobrý den,",
                paragraphs=["Obdrželi jsme žádost o změnu hesla. Pro nastavení nového hesla použijte tlačítko níže."],
                panels=[render_panel(title="Platnost odkazu", message="Odkaz platí 30 minut a lze jej použít pouze jednou. Pokud jste o změnu nežádali, tento e-mail ignorujte.")],
                cta_label="Obnovit heslo", cta_url=reset_url, accent="#f59e0b",
            ),
        )
    except Exception:
        # Do not expose provider errors, credentials, addresses or reset links.
        logger.error("Password recovery delivery failed")
        db.query(Customer).filter(Customer.id == customer.id, Customer.reset_token == digest).update(
            {Customer.reset_token: None, Customer.reset_token_expires: None}, synchronize_session=False)
        db.commit()
    return result


@router.get("/reset-password.html", response_class=HTMLResponse)
def reset_password_page():
    web_path = Path(__file__).parent.parent.parent.parent / "web" / "reset-password.html"
    if web_path.exists():
        return FileResponse(web_path)
    raise HTTPException(status_code=404, detail="Reset password page not found")


@router.post("/user/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db=Depends(get_db)):
    _limit_auth(request, "password-reset", calls=10)
    _validate_password(payload.new_password)
    digest = "sha256:" + hashlib.sha256(payload.token.encode()).hexdigest()
    # Lock the row: concurrent submissions cannot consume the same token twice.
    customer = db.query(Customer).filter(
        Customer.reset_token == digest,
        Customer.reset_token_expires > datetime.utcnow(),
    ).with_for_update().first()
    if not customer or customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(400, "Neplatný nebo expirovaný odkaz. Požádejte o nový.")
    customer.password_hash = hash_password(payload.new_password)
    customer.reset_token = None
    customer.reset_token_expires = None
    customer.session_version = customer_session_version(customer) + 1
    db.commit()
    return {"message": "Heslo bylo změněno. Přihlaste se novým heslem na všech zařízeních."}


class EmailVerificationRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)


@router.get("/user/email-verification")
def email_verification_status(email=Depends(get_current_user_email), db=Depends(get_db)):
    customer = get_customer_by_email(db, email)
    row = db.get(EmailVerification, customer.id)
    return {"required": bool(row and not row.verified_at), "verified": bool(row and row.verified_at)}


@router.post("/user/email-verification/resend")
def resend_email_verification(request: Request, email=Depends(get_current_user_email), db=Depends(get_db)):
    _limit_auth(request, "verify-resend", email, calls=3)
    customer = get_customer_by_email(db, email)
    row = db.get(EmailVerification, customer.id)
    if row is None:
        return {"message": "Pro tento účet nové ověření e-mailu není vyžadované."}
    if row.verified_at:
        return {"message": "E-mail už je ověřený."}
    if not issue_verification(db, customer):
        raise HTTPException(503, "E-mail se nepodařilo odeslat. Zkuste to později.")
    return {"message": "Ověřovací odkaz jsme odeslali na váš e-mail."}


@router.post("/user/email-verification/confirm")
def confirm_email_verification(payload: EmailVerificationRequest, request: Request, db=Depends(get_db)):
    _limit_auth(request, "verify-confirm", calls=10)
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    row = db.query(EmailVerification).filter(
        EmailVerification.token_digest == digest
    ).with_for_update().first()
    customer = db.get(Customer, row.customer_id) if row else None
    if (not row or row.verified_at or not row.expires_at or row.expires_at <= datetime.utcnow()
            or not customer or customer_is_deleted(customer) or customer_is_disabled(customer)):
        raise HTTPException(400, "Odkaz není platný nebo již byl použit. Vyžádejte si nový v aplikaci.")
    row.verified_at = datetime.utcnow()
    row.token_digest = None
    row.expires_at = None
    db.commit()
    return {"message": "E-mail je ověřený. Vraťte se do aplikace a klepněte na Zkontrolovat ověření."}
