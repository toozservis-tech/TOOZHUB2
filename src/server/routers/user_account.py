from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.core.auth import get_current_user_email
from src.core.security import hash_password, verify_password
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

    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(customer, field):
            setattr(customer, field, value)

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

    if not payload.export_downloaded:
        raise HTTPException(
            status_code=400,
            detail="Před smazáním účtu je nutné stáhnout export dat.",
        )

    if not customer.password_hash or not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")

    try:
        deleted_counts = delete_customer_account(customer, email=email, db=db)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Smazání účtu selhalo: {exc}",
        ) from exc

    return DeleteAccountResponse(
        deleted=True,
        message="Účet i navázaná data byly trvale smazány.",
        deleted_counts=deleted_counts,
    )


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

    if not verify_password(password_data.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")

    if not password_data.new_password or len(password_data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nové heslo musí mít alespoň 6 znaků")

    customer.password_hash = hash_password(password_data.new_password)
    db.commit()

    email_sent = False
    email_error = None
    email_service = EmailService()

    try:
        if email_service.is_configured():
            print(f"[CHANGE_PASSWORD] Odesílám potvrzovací email na: {email}")
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
                    html_body=html_body,
                )
                email_sent = True
                print(f"[CHANGE_PASSWORD] OK: Potvrzovací email úspěšně odeslán na: {email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[CHANGE_PASSWORD] ERROR: Chyba při odesílání emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print("[CHANGE_PASSWORD] WARNING: Email není nakonfigurován (chybí SMTP údaje)")
    except Exception as exc:
        email_error = str(exc)
        print(f"[CHANGE_PASSWORD] ERROR: Neočekávaná chyba: {email_error}")
        import traceback
        traceback.print_exc()

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
        "password_changed": True,
    }
