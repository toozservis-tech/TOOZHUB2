from __future__ import annotations

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.core.auth import get_current_user_email
from src.core.branding import APP_DISPLAY_NAME, APP_SUPPORT_DISPLAY_NAME
from src.core.security import verify_password, create_access_token, decode_access_token_payload
from src.core import mfa
from src.modules.vehicle_hub.account_state import increment_customer_session_version
from src.server.routers.user_auth import _limit_auth
from src.modules.email_client.templates import render_email_layout, render_list, render_panel
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer
from src.server.main_helpers import (
    BiometricSecurityPreferenceRequest,
    SecuritySettingsResponse,
    SupportContactRequest,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpSetupResponse,
    TotpSetupRequest,
    get_customer_by_email,
    normalize_email,
)
from src.server.security_helpers import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    build_totp_uri,
    generate_totp_secret,
    get_or_create_security_settings,
)
from src.server.security_tracking import extract_client_ip, log_security_event, log_user_activity


router = APIRouter()


@router.get("/user/security/settings", response_model=SecuritySettingsResponse)
def get_security_settings(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = get_or_create_security_settings(db, customer)
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_security_settings_read"},
    )

    return SecuritySettingsResponse(
        two_factor_enabled=bool(settings.two_factor_enabled),
        totp_configured=bool(settings.totp_secret),
        biometric_enabled=bool(settings.biometric_enabled),
        biometric_preferred=bool(settings.biometric_preferred),
    )


@router.post("/user/security/totp/setup", response_model=TotpSetupResponse)
def setup_totp(
    payload: TotpSetupRequest,
    request: Request,
    response: Response,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    _limit_auth(request, "totp-setup", customer.email, calls=5)
    mfa.limit_attempt(db, customer.id, "totp-setup")
    if not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(400, "Neplatné současné heslo")
    settings = mfa.locked_settings(db, customer)
    if settings.two_factor_enabled:
        raise HTTPException(409, "Dvoufázové ověření už je aktivní. Nové nastavení nesmí vypnout současnou ochranu.")
    response.headers["Cache-Control"] = "no-store"
    secret = generate_totp_secret()
    settings.totp_secret = mfa.protect_secret(secret)
    settings.totp_enabled_at = None
    state = mfa.state_for(db, customer.id)
    state.pending_expires_at = datetime.utcnow() + timedelta(minutes=10)
    state.last_step = -1
    db.commit()

    log_security_event(
        event_type="totp_setup_started",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return TotpSetupResponse(
        secret=secret,
        otpauth_uri=build_totp_uri(secret, customer.email),
        digits=TOTP_DIGITS,
        period_seconds=TOTP_PERIOD_SECONDS,
        message="Naskenujte klíč v aplikaci Google/Microsoft Authenticator a potvrďte 6místným kódem.",
    )


@router.post("/user/security/totp/enable")
def enable_totp(
    payload: TotpEnableRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    _limit_auth(request, "totp-code", customer.email, calls=5)
    mfa.limit_attempt(db, customer.id, "totp-code")
    settings = mfa.locked_settings(db, customer)
    if settings.two_factor_enabled:
        raise HTTPException(409, "Dvoufázové ověření už je aktivní.")
    state = mfa.state_for(db, customer.id)
    if not settings.totp_secret or not state.pending_expires_at or state.pending_expires_at <= datetime.utcnow():
        raise HTTPException(400, "Nastavení ověření vypršelo. Začněte znovu se současným heslem.")
    if not mfa.consume_code(db, settings, payload.code):
        raise HTTPException(400, "Neplatný nebo již použitý kód. Vyčkejte na další kód v autentikátoru.")
    settings.two_factor_enabled = True
    settings.totp_enabled_at = datetime.utcnow()
    state.pending_expires_at = None
    increment_customer_session_version(customer)
    claims = mfa.verified_claims(customer) if settings.two_factor_enabled else {"sub": customer.email, "sv": customer.session_version}
    db.commit()

    log_security_event(
        event_type="totp_enabled",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return {"message": "Dvoufázové ověření bylo aktivováno. Ostatní přihlášení byla ukončena.", "two_factor_enabled": True,
            "access_token": create_access_token(claims)}


@router.post("/user/security/totp/disable")
def disable_totp(
    payload: TotpDisableRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    if (customer.role or "").strip().lower() in {"admin", "developer_admin"}:
        raise HTTPException(403, "Administrátorský účet musí mít dvoufázové ověření aktivní.")
    _limit_auth(request, "totp-disable", customer.email, calls=5)
    mfa.limit_attempt(db, customer.id, "totp-disable")
    if not customer.password_hash or not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Neplatné současné heslo")

    settings = mfa.locked_settings(db, customer)
    if not settings.two_factor_enabled or not settings.totp_secret:
        raise HTTPException(status_code=400, detail="2FA není aktivní")

    if not mfa.consume_code(db, settings, payload.code):
        raise HTTPException(status_code=400, detail="Neplatný 2FA kód")

    settings.two_factor_enabled = False
    settings.totp_secret = None
    settings.totp_enabled_at = None
    mfa.state_for(db, customer.id).pending_expires_at = None
    increment_customer_session_version(customer)
    claims = mfa.verified_claims(customer) if settings.two_factor_enabled else {"sub": customer.email, "sv": customer.session_version}
    db.commit()

    log_security_event(
        event_type="totp_disabled",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return {"message": "Dvoufázové ověření bylo vypnuto. Ostatní přihlášení byla ukončena.", "two_factor_enabled": False,
            "access_token": create_access_token(claims)}


@router.get("/user/security/admin-status")
def admin_status(request: Request, response: Response, email: str = Depends(get_current_user_email), db=Depends(get_db)):
    customer = get_customer_by_email(db, email)
    claims = decode_access_token_payload(request.headers.get("authorization", "").removeprefix("Bearer ")) or {}
    response.headers["Cache-Control"] = "no-store"
    return mfa.admin_assurance_status(db, customer, claims)


@router.post("/user/security/admin-verify")
def verify_admin(payload: TotpDisableRequest, request: Request, response: Response,
                 email: str = Depends(get_current_user_email), db=Depends(get_db)):
    customer = get_customer_by_email(db, email)
    if (customer.role or "").strip().lower() not in {"admin", "developer_admin"}:
        raise HTTPException(403, "Tato kontrola je určena administrátorům.")
    _limit_auth(request, "admin-step-up", customer.email, calls=5)
    mfa.limit_attempt(db, customer.id, "admin-step-up")
    if not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(400, "Heslo nebo ověřovací kód nesouhlasí.")
    settings = mfa.locked_settings(db, customer)
    if not settings.two_factor_enabled:
        raise HTTPException(409, "Nejprve nastavte dvoufázové ověření.")
    if not mfa.consume_code(db, settings, payload.code):
        raise HTTPException(400, "Heslo nebo kód nesouhlasí, nebo už byl kód použit. Vyčkejte na nový kód.")
    claims = mfa.verified_claims(customer)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    log_security_event(event_type="admin_verified", request=request, user_email=customer.email,
                       customer_id=customer.id, tenant_id=customer.tenant_id,
                       endpoint=str(request.url.path), details={"method": "password_totp"})
    return {"access_token": create_access_token(claims),
            "message": "Administrátor ověřen na 15 minut."}


@router.post("/user/security/biometric")
def update_biometric_preference(
    payload: BiometricSecurityPreferenceRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = get_or_create_security_settings(db, customer)
    settings.biometric_enabled = bool(payload.enabled)
    settings.biometric_preferred = bool(payload.preferred) if payload.preferred is not None else bool(payload.enabled)
    db.commit()

    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={
            "source": "user_biometric_preference",
            "enabled": bool(payload.enabled),
            "preferred": bool(settings.biometric_preferred),
        },
    )

    return {
        "message": "Biometrická preference byla uložena. Pro plné biometrické přihlášení je nutné mít aktivní Passkey/WebAuthn tok v klientovi.",
        "biometric_enabled": bool(settings.biometric_enabled),
        "biometric_preferred": bool(settings.biometric_preferred),
    }


@router.post("/user/support")
def contact_support(
    payload: SupportContactRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    from src.modules.email_client.service import EmailService

    normalized_email = normalize_email(email)
    customer = get_customer_by_email(db, normalized_email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    category = (payload.category or "obecné").strip()[:64]
    subject = (payload.subject or "").strip()
    message = (payload.message or "").strip()
    phone = (payload.phone or "").strip() or None

    if len(subject) < 3:
        raise HTTPException(status_code=400, detail="Předmět musí mít alespoň 3 znaky")
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Zpráva musí mít alespoň 10 znaků")

    support_email = (
        os.getenv("SUPPORT_EMAIL", "").strip()
        or os.getenv("SMTP_FROM", "").strip()
        or os.getenv("SMTP_USER", "").strip()
    )
    if not support_email:
        raise HTTPException(
            status_code=503,
            detail="Podpora není dostupná - chybí konfigurace cílového emailu",
        )

    source_ip = extract_client_ip(request)
    created_at = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    app_url = (payload.page_url or "").strip() or None
    user_agent = (payload.user_agent or "").strip() or request.headers.get("user-agent")

    diagnostic_lines = []
    if payload.include_diagnostics:
        diagnostic_lines.append(f"IP: {source_ip or '-'}")
        diagnostic_lines.append(f"Tenant ID: {customer.tenant_id}")
        if app_url:
            diagnostic_lines.append(f"URL: {app_url}")
        if user_agent:
            diagnostic_lines.append(f"User-Agent: {user_agent}")

    diagnostics_text = "\n".join(diagnostic_lines) if diagnostic_lines else "Nezahrnuto"
    subject_line = f"[{APP_SUPPORT_DISPLAY_NAME}] [{category}] {subject}"
    body = (
        f"Nová zpráva z panelu podpory\n\n"
        f"Datum: {created_at}\n"
        f"Uživatel: {customer.name or '-'}\n"
        f"Email: {customer.email}\n"
        f"Telefon: {phone or customer.phone or '-'}\n"
        f"Kategorie: {category}\n"
        f"Předmět: {subject}\n\n"
        f"Zpráva:\n{message}\n\n"
        f"Diagnostika:\n{diagnostics_text}\n"
    )

    html_body = render_email_layout(
        title="Nová zpráva na podporu",
        subtitle="Požadavek odeslaný z klientské aplikace.",
        intro="Do podpory přišla nová zpráva.",
        panels=[
            render_panel(
                title="Odesílatel",
                rows=[
                    ("Datum", created_at),
                    ("Uživatel", customer.name or "-"),
                    ("Email", customer.email),
                    ("Telefon", phone or customer.phone or "-"),
                    ("Kategorie", category),
                    ("Předmět", subject),
                ],
                accent="#3b82f6",
                tone="#eff6ff",
            ),
            render_panel(
                title="Zpráva",
                message=message,
            ),
            render_panel(
                title="Diagnostika",
                raw_html=render_list(diagnostic_lines or ["Nezahrnuto"]),
                accent="#64748b",
                tone="#f8fafc",
            ),
        ],
        accent="#f59e0b",
        footer_note=f"Interní e-mail podpory · {APP_SUPPORT_DISPLAY_NAME}",
    )

    email_service = EmailService()
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Podpora není dostupná - SMTP není nakonfigurováno",
        )

    try:
        email_service.send_simple_email(
            to=support_email,
            subject=subject_line,
            body=body,
            html_body=html_body,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Nepodařilo se odeslat zprávu podpory: {exc}") from exc

    log_security_event(
        event_type="support_contact_submitted",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={
            "category": category,
            "subject": subject[:120],
            "has_phone": bool(phone),
            "include_diagnostics": bool(payload.include_diagnostics),
        },
    )

    return {"message": "Požadavek byl odeslán na podporu."}
