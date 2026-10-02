from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

from src.core.auth import get_current_user_email
from src.core.branding import APP_DISPLAY_NAME
from src.core.security import hash_password, verify_password, validate_new_password
from src.modules.vehicle_hub.account_state import customer_session_version
from src.server.routers.user_auth import _limit_auth
from src.modules.email_client.templates import render_email_layout, render_panel
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer
from src.server.main_helpers import (
    ACCOUNT_DELETE_CONFIRM_TOKENS,
    APP_VERSION,
    ChangePasswordRequest,
    DeleteAccountRequest,
    DeleteAccountResponse,
    UserResponse,
    UserUpdate,
    cleanup_export_dir,
    delete_customer_account,
    export_current_customer_bundle,
    get_customer_by_email,
    normalize_delete_confirmation,
)
from src.server.security_tracking import log_user_activity


router = APIRouter()


@router.get("/user/me", response_model=UserResponse)
def get_current_user(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_me"},
    )
    return customer


@router.put("/user/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_update_profile"},
    )

    from src.modules.vehicle_hub.workshop_address import apply_workshop_address
    from src.core.rbac import is_service_or_admin
    if user_update.workshop_same_as_registered is not None and not is_service_or_admin(customer.role):
        raise HTTPException(403, "Provozovnu může nastavit servis nebo administrátor.")
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if not field.startswith("workshop_") and hasattr(customer, field):
            setattr(customer, field, value)

    apply_workshop_address(customer, user_update)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/user/me/export")
def export_current_user_data(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    tmp_dir_path, zip_path, export_file_name, vehicle_count = export_current_customer_bundle(
        customer,
        email=email,
        db=db,
        app_version=APP_VERSION,
    )

    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_export_data", "vehicles": vehicle_count},
    )

    return FileResponse(
        path=str(zip_path),
        filename=export_file_name,
        media_type="application/zip",
        background=BackgroundTask(cleanup_export_dir, tmp_dir_path),
    )


@router.delete("/user/me", response_model=DeleteAccountResponse)
def delete_current_user_account(
    payload: DeleteAccountRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    confirmation = normalize_delete_confirmation(payload.confirmation_text)
    if confirmation not in ACCOUNT_DELETE_CONFIRM_TOKENS:
        raise HTTPException(
            status_code=400,
            detail="Potvrzení smazání nesouhlasí. Zadejte přesně text: SMAZAT UCET",
        )

    _limit_auth(request, "delete-account", customer.email, calls=5)
    if not customer.password_hash or not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")

    try:
        db.info["requested_erasure_receipt"] = payload.erasure_receipt
        deleted_counts = delete_customer_account(customer, email=email, db=db)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Účet se nepodařilo odstranit. Žádná změna nebyla potvrzena. Zkuste to později.",
        ) from exc

    return DeleteAccountResponse(
        deleted=True,
        deletion_receipt=db.info.pop("account_erasure_receipt", None),
        files_pending=deleted_counts.get("private_files_queued", 0),
        message="Účet a jeho obsah byly odstraněny. Soukromé soubory se dokončují mazat na pozadí. "
                "Údaje o platbách potřebné pro účetnictví a ochranu nákupů zůstávají uchované.",
        deleted_counts=deleted_counts,
    )


class ErasureStatusRequest(BaseModel):
    receipt: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/user/account-erasure/status")
def account_erasure_status(payload: ErasureStatusRequest, request: Request, response: Response, db=Depends(get_db)):
    from src.core.file_erasure import receipt_status
    _limit_auth(request, "erasure-status", payload.receipt, calls=60)
    response.headers["Cache-Control"] = "no-store"
    result = receipt_status(db, payload.receipt)
    if result is None:
        raise HTTPException(404, "Potvrzení odstranění nebylo nalezeno nebo již skončila jeho platnost.")
    db.commit()
    return result


@router.put("/user/change-password")
def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    from src.modules.email_client.service import EmailService

    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_change_password"},
    )

    if not customer.password_hash:
        raise HTTPException(status_code=400, detail="Uživatel nemá nastavené heslo")

    _limit_auth(request, "change-password", email, calls=5)
    if not verify_password(password_data.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")

    try:
        validate_new_password(password_data.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    customer.password_hash = hash_password(password_data.new_password)
    customer.session_version = customer_session_version(customer) + 1
    customer.reset_token = None
    customer.reset_token_expires = None
    db.commit()

    email_sent = False
    email_error = None
    email_service = EmailService()

    try:
        if email_service.is_configured():
            print("[CHANGE_PASSWORD] Sending security notification")
            user_name = customer.name or "Uživateli"
            change_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")

            email_body = f"""
Dobrý den {user_name},

vaše heslo k účtu v aplikaci {APP_DISPLAY_NAME} bylo úspěšně změněno.

Změna byla provedena: {change_time} UTC

Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu.

S pozdravem,
{APP_DISPLAY_NAME}
"""
            html_body = render_email_layout(
                title="Heslo bylo změněno",
                subtitle="Bezpečnostní potvrzení změny hesla.",
                intro=f"Dobrý den {user_name},",
                paragraphs=[
                    f"vaše heslo k účtu v aplikaci {APP_DISPLAY_NAME} bylo úspěšně změněno.",
                    "Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu a změňte přístupové údaje.",
                ],
                panels=[
                    render_panel(
                        title="Detaily změny",
                        rows=[("Datum změny", f"{change_time} UTC"), ("Účet", email)],
                        accent="#ef4444",
                        tone="#fef2f2",
                    )
                ],
                accent="#f59e0b",
            )
            try:
                email_sent = bool(email_service.send_simple_email(
                    to=email,
                    subject=f"Potvrzení změny hesla - {APP_DISPLAY_NAME}",
                    body=email_body,
                    html_body=html_body,
                ))
                if not email_sent:
                    email_error = "delivery_failed"
                print("[CHANGE_PASSWORD] Security notification accepted" if email_sent else "[CHANGE_PASSWORD] Security notification delivery failed")
            except Exception:
                email_error = "delivery_failed"
                print("[CHANGE_PASSWORD] Security notification delivery failed")
        else:
            print("[CHANGE_PASSWORD] WARNING: Email není nakonfigurován (chybí SMTP údaje)")
    except Exception:
        email_error = "delivery_failed"
        print("[CHANGE_PASSWORD] Security notification unavailable")

    response_message = "Heslo bylo úspěšně změněno"
    if email_sent:
        response_message += " a potvrzovací email byl odeslán"
    elif email_error:
        response_message += " (potvrzovací e-mail se nepodařilo odeslat)"
    else:
        response_message += " (email není nakonfigurován)"

    return {
        "message": response_message,
        "email_sent": email_sent,
        "password_changed": True,
    }
