import json
import hashlib
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceFakturywebSettings,
    ServiceFakturywebInvoice,
    ServiceFakturywebAuditLog,
)
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from .fakturyweb_client import FakturyWebTestClient, FakturyWebError

router = APIRouter(prefix="/api/v1/services/workspace/fakturyweb", tags=["service-workspace-fakturyweb"])

def _require_service_role(current_user: Customer) -> None:
    role = str(getattr(current_user, "role", "") or "").lower()
    if role != "service":
        raise HTTPException(status_code=403, detail="FakturyWeb test integraci může spravovat pouze servisní účet.")

def _encrypt_api_key(api_key: str) -> str:
    # Placeholder for actual encryption (e.g. Fernet/KMS)
    import base64
    return base64.b64encode(api_key.encode("utf-8")).decode("utf-8")

def _decrypt_api_key(encrypted_key: str) -> str:
    # Placeholder for actual decryption
    import base64
    return base64.b64decode(encrypted_key.encode("utf-8")).decode("utf-8")

def _mask_api_key(api_key: str) -> str:
    if not api_key or len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}****{api_key[-4:]}"

def _log_audit(
    db: Session,
    tenant_id: int,
    user_id: int,
    action: str,
    endpoint: str,
    request_payload: dict,
    response_status: Optional[str] = None,
    response_status_id: Optional[int] = None,
    error_message: Optional[str] = None,
    local_invoice_id: Optional[int] = None,
):
    # Hash request payload to avoid storing PII
    req_str = json.dumps(request_payload, sort_keys=True)
    req_hash = hashlib.sha256(req_str.encode("utf-8")).hexdigest()
    
    log = ServiceFakturywebAuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        local_invoice_id=local_invoice_id,
        endpoint=endpoint,
        request_hash=req_hash,
        response_status=response_status,
        response_status_id=response_status_id,
        error_message=error_message,
    )
    db.add(log)
    db.commit()

class SettingsResponse(BaseModel):
    configured: bool
    email: Optional[str] = None
    supplier_mode: Optional[str] = None
    d_id: Optional[str] = None
    test_mode_default: bool = True
    last_test_at: Optional[datetime] = None
    last_error: Optional[str] = None
    custom_d_name: Optional[str] = None
    custom_d_street: Optional[str] = None
    custom_d_city: Optional[str] = None
    custom_d_zip: Optional[str] = None
    custom_d_state: Optional[str] = None
    custom_d_ico: Optional[str] = None
    custom_d_dic: Optional[str] = None
    custom_d_email: Optional[str] = None
    custom_d_phone: Optional[str] = None
    custom_d_web: Optional[str] = None
    custom_d_bankaccount: Optional[str] = None

class SettingsSaveRequest(BaseModel):
    fakturyweb_email: str
    fakturyweb_api_key: str
    supplier_mode: str
    fakturyweb_d_id: Optional[str] = None
    default_due_days: int = 7
    default_payment: str = "prevod"
    default_currency: str = "Kč"
    default_style: str = "styl_7"
    default_qr: int = 1
    custom_d_name: Optional[str] = None
    custom_d_street: Optional[str] = None
    custom_d_city: Optional[str] = None
    custom_d_zip: Optional[str] = None
    custom_d_state: Optional[str] = None
    custom_d_ico: Optional[str] = None
    custom_d_dic: Optional[str] = None
    custom_d_email: Optional[str] = None
    custom_d_phone: Optional[str] = None
    custom_d_web: Optional[str] = None
    custom_d_bankaccount: Optional[str] = None

@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    if not settings:
        return SettingsResponse(configured=False)
        
    return SettingsResponse(
        configured=True,
        email=settings.email,
        supplier_mode=settings.supplier_mode,
        d_id=settings.d_id,
        test_mode_default=settings.test_mode_default,
        last_test_at=settings.last_test_at,
        last_error=settings.last_error,
        custom_d_name=settings.custom_d_name,
        custom_d_street=settings.custom_d_street,
        custom_d_city=settings.custom_d_city,
        custom_d_zip=settings.custom_d_zip,
        custom_d_state=settings.custom_d_state,
        custom_d_ico=settings.custom_d_ico,
        custom_d_dic=settings.custom_d_dic,
        custom_d_email=settings.custom_d_email,
        custom_d_phone=settings.custom_d_phone,
        custom_d_web=settings.custom_d_web,
        custom_d_bankaccount=settings.custom_d_bankaccount,
    )

@router.post("/settings")
def save_settings(
    payload: SettingsSaveRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    if not settings:
        settings = ServiceFakturywebSettings(
            tenant_id=current_user.tenant_id,
            service_workspace_id=current_user.id,
        )
        db.add(settings)
        
    settings.email = payload.fakturyweb_email
    
    # Only update API key if it's not masked (meaning user entered a new one)
    if not payload.fakturyweb_api_key.endswith("****") and "****" not in payload.fakturyweb_api_key:
        settings.encrypted_api_key = _encrypt_api_key(payload.fakturyweb_api_key)
        settings.api_key_mask = _mask_api_key(payload.fakturyweb_api_key)
        
    settings.supplier_mode = payload.supplier_mode
    settings.d_id = payload.fakturyweb_d_id
    settings.default_due_days = payload.default_due_days
    settings.default_payment = payload.default_payment
    settings.default_currency = payload.default_currency
    settings.default_style = payload.default_style
    settings.default_qr = payload.default_qr
    settings.test_mode_default = True
    
    settings.custom_d_name = payload.custom_d_name
    settings.custom_d_street = payload.custom_d_street
    settings.custom_d_city = payload.custom_d_city
    settings.custom_d_zip = payload.custom_d_zip
    settings.custom_d_state = payload.custom_d_state
    settings.custom_d_ico = payload.custom_d_ico
    settings.custom_d_dic = payload.custom_d_dic
    settings.custom_d_email = payload.custom_d_email
    settings.custom_d_phone = payload.custom_d_phone
    settings.custom_d_web = payload.custom_d_web
    settings.custom_d_bankaccount = payload.custom_d_bankaccount
    
    db.commit()
    
    _log_audit(
        db, tenant_id=current_user.tenant_id, user_id=current_user.id,
        action="settings_saved", endpoint="/settings", request_payload={"email": payload.fakturyweb_email}
    )
    
    return {"ok": True}

@router.post("/test-connection")
def test_connection(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    if not settings or not settings.encrypted_api_key:
        raise HTTPException(status_code=400, detail="Nastavení API není kompletní.")
        
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            client.call_fakturyweb("api/init", {"key": api_key, "email": settings.email})
            
        settings.last_test_at = datetime.utcnow()
        settings.last_error = None
        db.commit()
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="connection_tested", endpoint="/api/init", request_payload={"email": settings.email},
            response_status="OK", response_status_id=1
        )
        return {"ok": True, "status": 1, "message": "Spojení bylo úspěšné."}
        
    except FakturyWebError as e:
        settings.last_test_at = datetime.utcnow()
        settings.last_error = str(e)
        db.commit()
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="connection_tested", endpoint="/api/init", request_payload={"email": settings.email},
            response_status="ERROR", response_status_id=e.status, error_message=str(e)
        )
        return {"ok": False, "status": e.status, "message": str(e)}

class InvoiceCustomer(BaseModel):
    name: str
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    state: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    email: Optional[str] = None

class InvoiceDetails(BaseModel):
    issue_date: str
    delivery_date: str
    due_date: str
    payment: str
    currency: str
    note: Optional[str] = None
    internal_note: Optional[str] = None
    qr: int = 1
    style: str = "styl_7"

class InvoiceItem(BaseModel):
    text: str
    quantity: float
    unit: str
    price: float
    vat: Optional[float] = None

class InvoiceCreateRequest(BaseModel):
    customer: InvoiceCustomer
    invoice: InvoiceDetails
    items: List[InvoiceItem]

@router.post("/invoices/test-create")
def create_test_invoice(
    payload: InvoiceCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    if not settings or not settings.encrypted_api_key:
        raise HTTPException(status_code=400, detail="Nastavení API není kompletní.")
        
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    
    fw_payload = {
        "key": api_key,
        "email": settings.email,
        "apitest": 1,
    }
    
    if settings.supplier_mode == "saved_company" and settings.d_id:
        fw_payload["d"] = {"d_id": settings.d_id}
    else:
        # manual mode - use custom fields if provided, else fallback to service profile
        fw_payload["d"] = {
            "d_name": settings.custom_d_name or current_user.name or "Test Servis",
            "d_street": settings.custom_d_street or current_user.street,
            "d_city": settings.custom_d_city or current_user.city,
            "d_zip": settings.custom_d_zip or current_user.zip,
            "d_state": settings.custom_d_state or "CZ",
            "d_ico": settings.custom_d_ico or current_user.ico,
            "d_dic": settings.custom_d_dic or current_user.dic,
            "d_email": settings.custom_d_email or current_user.email,
            "d_phone": settings.custom_d_phone or current_user.phone,
            "d_web": settings.custom_d_web,
            "d_bankaccount": settings.custom_d_bankaccount,
        }
        # Remove None values
        fw_payload["d"] = {k: v for k, v in fw_payload["d"].items() if v is not None}
        
    fw_payload["o"] = {
        "o_name": payload.customer.name,
        "o_street": payload.customer.street,
        "o_city": payload.customer.city,
        "o_zip": payload.customer.zip,
        "o_state": payload.customer.state,
        "o_ico": payload.customer.ico,
        "o_dic": payload.customer.dic,
        "o_email": payload.customer.email,
    }
    
    fw_payload["f"] = {
        "f_date_issue": payload.invoice.issue_date,
        "f_date_delivery": payload.invoice.delivery_date,
        "f_date_due": payload.invoice.due_date,
        "f_payment": payload.invoice.payment,
        "f_currency": payload.invoice.currency,
        "f_type": 1,
        "f_qr": payload.invoice.qr,
        "f_style": payload.invoice.style,
        "f_language": "CS",
        "f_note": payload.invoice.note,
        "f_internal_note": payload.invoice.internal_note,
        "f_tags": ["Správa vozidel", "TEST"],
    }
    
    fw_items = []
    for item in payload.items:
        it = {
            "p_text": item.text,
            "p_quantity": item.quantity,
            "p_unit": item.unit,
            "p_price": item.price,
        }
        if item.vat is not None:
            it["p_vat"] = item.vat
        fw_items.append(it)
        
    fw_payload["p"] = fw_items
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            resp = client.call_fakturyweb("api/nf", fw_payload)
            
        code = resp.get("code")
        number = resp.get("number")
        
        total_estimated = sum(item.quantity * item.price for item in payload.items)
        
        inv = ServiceFakturywebInvoice(
            tenant_id=current_user.tenant_id,
            service_workspace_id=current_user.id,
            created_by_user_id=current_user.id,
            fakturyweb_code=code,
            fakturyweb_number=number,
            test_mode=True,
            customer_name=payload.customer.name,
            customer_email=payload.customer.email,
            issue_date=datetime.strptime(payload.invoice.issue_date, "%Y-%m-%d").date(),
            due_date=datetime.strptime(payload.invoice.due_date, "%Y-%m-%d").date(),
            amount_estimated=total_estimated,
            local_status="created",
            remote_status_raw=json.dumps(resp),
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="test_invoice_created", endpoint="/api/nf", request_payload=fw_payload,
            response_status="OK", response_status_id=1, local_invoice_id=inv.id
        )
        
        return {"ok": True, "id": inv.id, "code": code, "number": number}
        
    except FakturyWebError as e:
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="test_invoice_created", endpoint="/api/nf", request_payload=fw_payload,
            response_status="ERROR", response_status_id=e.status, error_message=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/invoices")
def list_local_invoices(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    invoices = db.query(ServiceFakturywebInvoice).filter(
        ServiceFakturywebInvoice.tenant_id == current_user.tenant_id,
        ServiceFakturywebInvoice.service_workspace_id == current_user.id
    ).order_by(ServiceFakturywebInvoice.id.desc()).all()
    
    return [{
        "id": inv.id,
        "fakturyweb_code": inv.fakturyweb_code,
        "fakturyweb_number": inv.fakturyweb_number,
        "customer_name": inv.customer_name,
        "amount_estimated": float(inv.amount_estimated) if inv.amount_estimated else None,
        "issue_date": inv.issue_date,
        "due_date": inv.due_date,
        "local_status": inv.local_status,
        "test_mode": inv.test_mode,
        "pdf_url": inv.pdf_url,
    } for inv in invoices]

@router.post("/invoices/{local_id}/view")
def view_invoice(
    local_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    inv = db.query(ServiceFakturywebInvoice).filter(
        ServiceFakturywebInvoice.id == local_id,
        ServiceFakturywebInvoice.tenant_id == current_user.tenant_id,
        ServiceFakturywebInvoice.service_workspace_id == current_user.id
    ).first()
    
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena.")
        
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    
    payload = {"key": api_key, "email": settings.email, "code": inv.fakturyweb_code}
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            resp = client.call_fakturyweb("api/zf", payload, requires_session=True)
            
        inv.pdf_url = resp.get("url")
        inv.fakturyweb_number = resp.get("number")
        inv.last_synced_at = datetime.utcnow()
        db.commit()
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_pdf_requested", endpoint="/api/zf", request_payload=payload,
            response_status="OK", response_status_id=1, local_invoice_id=inv.id
        )
        
        return {"ok": True, "pdf_url": inv.pdf_url, "number": inv.fakturyweb_number, "status": resp.get("status")}
        
    except FakturyWebError as e:
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_pdf_requested", endpoint="/api/zf", request_payload=payload,
            response_status="ERROR", response_status_id=e.status, error_message=str(e), local_invoice_id=inv.id
        )
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/invoices/{local_id}/status")
def get_invoice_status(
    local_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    inv = db.query(ServiceFakturywebInvoice).filter(
        ServiceFakturywebInvoice.id == local_id,
        ServiceFakturywebInvoice.tenant_id == current_user.tenant_id,
        ServiceFakturywebInvoice.service_workspace_id == current_user.id
    ).first()
    
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena.")
        
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    payload = {"key": api_key, "email": settings.email, "code": inv.fakturyweb_code}
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            resp = client.call_fakturyweb("api/status", payload, requires_session=True)
            
        inv.remote_status_raw = json.dumps(resp)
        inv.last_synced_at = datetime.utcnow()
        
        # Parse status from detail if available
        if resp.get("detail") and resp["detail"].get("status"):
            inv.local_status = resp["detail"]["status"]
            
        db.commit()
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_status_requested", endpoint="/api/status", request_payload=payload,
            response_status="OK", response_status_id=1, local_invoice_id=inv.id
        )
        
        return {"ok": True, "status": resp.get("status"), "detail": resp.get("detail")}
        
    except FakturyWebError as e:
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_status_requested", endpoint="/api/status", request_payload=payload,
            response_status="ERROR", response_status_id=e.status, error_message=str(e), local_invoice_id=inv.id
        )
        raise HTTPException(status_code=400, detail=str(e))

class MarkPaidRequest(BaseModel):
    date: str

@router.post("/invoices/{local_id}/mark-paid")
def mark_invoice_paid(
    local_id: int,
    payload: MarkPaidRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    inv = db.query(ServiceFakturywebInvoice).filter(
        ServiceFakturywebInvoice.id == local_id,
        ServiceFakturywebInvoice.tenant_id == current_user.tenant_id,
        ServiceFakturywebInvoice.service_workspace_id == current_user.id
    ).first()
    
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nenalezena.")
        
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    fw_payload = {"key": api_key, "email": settings.email, "code": inv.fakturyweb_code, "date": payload.date}
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            resp = client.call_fakturyweb("api/uf", fw_payload, requires_session=True)
            
        inv.local_status = "paid"
        db.commit()
        
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_mark_paid_requested", endpoint="/api/uf", request_payload=fw_payload,
            response_status="OK", response_status_id=1, local_invoice_id=inv.id
        )
        
        return {"ok": True, "result": resp}
        
    except FakturyWebError as e:
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="invoice_mark_paid_requested", endpoint="/api/uf", request_payload=fw_payload,
            response_status="ERROR", response_status_id=e.status, error_message=str(e), local_invoice_id=inv.id
        )
        raise HTTPException(status_code=400, detail=str(e))

class RemoteListRequest(BaseModel):
    type: str  # created, issued, delivered, paid
    date_from: Optional[str] = None
    date_to: Optional[str] = None

@router.post("/invoices/list-remote")
def list_remote_invoices(
    payload: RemoteListRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_role(current_user)
    settings = db.query(ServiceFakturywebSettings).filter(
        ServiceFakturywebSettings.tenant_id == current_user.tenant_id,
        ServiceFakturywebSettings.service_workspace_id == current_user.id
    ).first()
    
    if not settings or not settings.encrypted_api_key:
        raise HTTPException(status_code=400, detail="Nastavení API není kompletní.")
        
    api_key = _decrypt_api_key(settings.encrypted_api_key)
    
    if payload.type not in ["created", "issued", "delivered", "paid"]:
        raise HTTPException(status_code=400, detail="Neplatný typ seznamu.")
        
    fw_payload = {"key": api_key, "email": settings.email}
    if payload.date_from:
        fw_payload["date_from"] = payload.date_from
    if payload.date_to:
        fw_payload["date_to"] = payload.date_to
        
    endpoint = f"api/list/{payload.type}"
    
    try:
        with FakturyWebTestClient(api_key=api_key, email=settings.email) as client:
            resp = client.call_fakturyweb(endpoint, fw_payload, requires_session=True)
            
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="remote_list_requested", endpoint=endpoint, request_payload=fw_payload,
            response_status="OK", response_status_id=1
        )
        
        return {"ok": True, "data": resp}
        
    except FakturyWebError as e:
        _log_audit(
            db, tenant_id=current_user.tenant_id, user_id=current_user.id,
            action="remote_list_requested", endpoint=endpoint, request_payload=fw_payload,
            response_status="ERROR", response_status_id=e.status, error_message=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
