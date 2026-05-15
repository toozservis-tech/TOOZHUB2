"""REST API mzdového modulu pro servisní účet (payroll)."""
from __future__ import annotations

import csv
import zipfile
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    PayrollAttendance,
    PayrollEmployee,
    PayrollEmployeeOffice,
    PayrollJournal,
    PayrollJmhzSubmission,
    PayrollOffice,
    PayrollPayslip,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role

router = APIRouter(prefix="/api/service/payroll", tags=["service-payroll"])

PPV_ALLOWED = frozenset({"hpp", "dpp", "dpc"})
JMHC_STATES = frozenset({"nove", "odeslano", "prijato", "chyba"})
PAYSLIP_STATES = frozenset({"open", "closed"})


def _ensure_payroll_schema(db: Session) -> None:
    assert_module_ready(db, "service_payroll", detail_prefix="Mzdový modul není připraven (chybí migrace databáze)")


def _ensure_payroll_license(db: Session, current_user: Customer) -> None:
    """Schéma + tarif FULL (SERVICE FREE nesmí mzdy)."""
    from src.modules.licensing.service import assert_service_payroll_or_advanced_forbidden

    _ensure_payroll_schema(db)
    assert_service_payroll_or_advanced_forbidden(db, service_customer_id=int(current_user.id))


def _mask_sensitive_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    s = str(value).strip()
    if len(s) <= 4:
        return "****"
    return f"{s[:2]}…{s[-2:]}"


def _employee_snapshot(emp: PayrollEmployee, *, mask: bool) -> dict[str, Any]:
    def sens(v: Optional[str]) -> Optional[str]:
        return _mask_sensitive_id(v) if mask else v

    return {
        "id": emp.id,
        "primary_office_id": emp.primary_office_id,
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "birth_date": emp.birth_date.isoformat() if emp.birth_date else None,
        "birth_number": sens(emp.birth_number),
        "gender": emp.gender,
        "street": emp.street,
        "city": emp.city,
        "postal_code": emp.postal_code,
        "country_code": emp.country_code,
        "email": emp.email,
        "phone": emp.phone,
        "tax_residency_country": emp.tax_residency_country,
        "tax_resident": emp.tax_resident,
        "education_level": emp.education_level,
        "oic": emp.oic,
        "oic_assigned_at": emp.oic_assigned_at.isoformat() if emp.oic_assigned_at else None,
        "health_insurance_code": emp.health_insurance_code,
        "disability_degree": emp.disability_degree,
        "disability_from": emp.disability_from.isoformat() if emp.disability_from else None,
        "disability_to": emp.disability_to.isoformat() if emp.disability_to else None,
        "ztp_p": emp.ztp_p,
        "pension_type": emp.pension_type,
        "pension_from": emp.pension_from.isoformat() if emp.pension_from else None,
        "foreign_national": emp.foreign_national,
        "citizenship_code": emp.citizenship_code,
        "id_document_type": emp.id_document_type,
        "id_document_number": sens(emp.id_document_number),
        "id_document_issue_country": emp.id_document_issue_country,
        "residence_permit_until": emp.residence_permit_until.isoformat() if emp.residence_permit_until else None,
        "bank_account": sens(emp.bank_account),
        "iban": sens(emp.iban),
        "swift": emp.swift,
        "contract_hours_per_week": emp.contract_hours_per_week,
        "hourly_gross_rate": emp.hourly_gross_rate,
        "default_ppv": emp.default_ppv,
        "is_active": emp.is_active,
        "created_at": emp.created_at.isoformat() if emp.created_at else None,
        "updated_at": emp.updated_at.isoformat() if emp.updated_at else None,
    }


def _office_scope(db: Session, current_user: Customer, office_id: int) -> PayrollOffice:
    row = (
        db.query(PayrollOffice)
        .filter(
            PayrollOffice.id == office_id,
            PayrollOffice.tenant_id == int(current_user.tenant_id),
            PayrollOffice.service_id == int(current_user.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Účtárna nenalezena.")
    return row


def _employee_scope(db: Session, current_user: Customer, employee_id: int) -> PayrollEmployee:
    row = (
        db.query(PayrollEmployee)
        .filter(
            PayrollEmployee.id == employee_id,
            PayrollEmployee.tenant_id == int(current_user.tenant_id),
            PayrollEmployee.service_id == int(current_user.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Zaměstnanec nenalezen.")
    return row


def _compute_payout(att: PayrollAttendance, emp: PayrollEmployee) -> tuple[float, float, float, float, float, float, float]:
    """Zjednodušený výpočet: hodiny × sazba + příplatek přesčasů; odvody a zálohová daň orientační."""
    rate = float(emp.hourly_gross_rate or 0)
    regular = float(att.odpracovano_hodin or 0) * rate
    ot_premium = float(att.prescas_hodin or 0) * rate * 0.25
    gross = max(regular + ot_premium, 0.0)
    social = gross * 0.071
    health = gross * 0.045
    tax_base = max(gross - social - health, 0.0)
    tax = tax_base * 0.15
    net = max(tax_base - tax, 0.0)
    employer_cost = gross * 1.34
    return gross, social, health, tax, net, net, employer_cost


class PayrollOfficeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    vs_cssz: Optional[str] = Field(default=None, max_length=32)
    datovka_id: Optional[str] = Field(default=None, max_length=64)
    is_active: bool = True


class PayrollOfficeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    vs_cssz: Optional[str] = Field(default=None, max_length=32)
    datovka_id: Optional[str] = Field(default=None, max_length=64)
    is_active: Optional[bool] = None


class PayrollEmployeeCreate(BaseModel):
    primary_office_id: Optional[int] = Field(default=None, gt=0)
    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)
    birth_date: date
    birth_number: Optional[str] = Field(default=None, max_length=32)
    gender: Optional[str] = Field(default=None, max_length=16)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=128)
    postal_code: Optional[str] = Field(default=None, max_length=16)
    country_code: Optional[str] = Field(default=None, max_length=8)
    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=64)
    tax_residency_country: Optional[str] = Field(default=None, max_length=8)
    tax_resident: Optional[bool] = None
    education_level: Optional[str] = Field(default=None, max_length=64)
    oic: Optional[str] = Field(default=None, max_length=32)
    oic_assigned_at: Optional[date] = None
    health_insurance_code: Optional[str] = Field(default=None, max_length=16)
    disability_degree: Optional[str] = Field(default=None, max_length=32)
    disability_from: Optional[date] = None
    disability_to: Optional[date] = None
    ztp_p: bool = False
    pension_type: Optional[str] = Field(default=None, max_length=64)
    pension_from: Optional[date] = None
    foreign_national: bool = False
    citizenship_code: Optional[str] = Field(default=None, max_length=8)
    id_document_type: Optional[str] = Field(default=None, max_length=64)
    id_document_number: Optional[str] = Field(default=None, max_length=128)
    id_document_issue_country: Optional[str] = Field(default=None, max_length=8)
    residence_permit_until: Optional[date] = None
    bank_account: Optional[str] = Field(default=None, max_length=64)
    iban: Optional[str] = Field(default=None, max_length=64)
    swift: Optional[str] = Field(default=None, max_length=32)
    contract_hours_per_week: Optional[float] = Field(default=None, ge=0)
    hourly_gross_rate: Optional[float] = Field(default=None, ge=0)
    default_ppv: str = Field(default="hpp", max_length=16)
    is_active: bool = True


class PayrollEmployeeUpdate(BaseModel):
    primary_office_id: Optional[int] = Field(default=None, gt=0)
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    last_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    birth_date: Optional[date] = None
    birth_number: Optional[str] = Field(default=None, max_length=32)
    gender: Optional[str] = Field(default=None, max_length=16)
    street: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=128)
    postal_code: Optional[str] = Field(default=None, max_length=16)
    country_code: Optional[str] = Field(default=None, max_length=8)
    email: Optional[str] = Field(default=None, max_length=320)
    phone: Optional[str] = Field(default=None, max_length=64)
    tax_residency_country: Optional[str] = Field(default=None, max_length=8)
    tax_resident: Optional[bool] = None
    education_level: Optional[str] = Field(default=None, max_length=64)
    oic: Optional[str] = Field(default=None, max_length=32)
    oic_assigned_at: Optional[date] = None
    health_insurance_code: Optional[str] = Field(default=None, max_length=16)
    disability_degree: Optional[str] = Field(default=None, max_length=32)
    disability_from: Optional[date] = None
    disability_to: Optional[date] = None
    ztp_p: Optional[bool] = None
    pension_type: Optional[str] = Field(default=None, max_length=64)
    pension_from: Optional[date] = None
    foreign_national: Optional[bool] = None
    citizenship_code: Optional[str] = Field(default=None, max_length=8)
    id_document_type: Optional[str] = Field(default=None, max_length=64)
    id_document_number: Optional[str] = Field(default=None, max_length=128)
    id_document_issue_country: Optional[str] = Field(default=None, max_length=8)
    residence_permit_until: Optional[date] = None
    bank_account: Optional[str] = Field(default=None, max_length=64)
    iban: Optional[str] = Field(default=None, max_length=64)
    swift: Optional[str] = Field(default=None, max_length=32)
    contract_hours_per_week: Optional[float] = Field(default=None, ge=0)
    hourly_gross_rate: Optional[float] = Field(default=None, ge=0)
    default_ppv: Optional[str] = Field(default=None, max_length=16)
    is_active: Optional[bool] = None


class PayrollAttendanceUpdate(BaseModel):
    fond_hodin: Optional[float] = Field(default=None, ge=0)
    odpracovano_hodin: Optional[float] = Field(default=None, ge=0)
    dovolena_hodin: Optional[float] = Field(default=None, ge=0)
    nemoc_hodin: Optional[float] = Field(default=None, ge=0)
    prescas_hodin: Optional[float] = Field(default=None, ge=0)
    neomluvena_absence_hodin: Optional[float] = Field(default=None, ge=0)
    pritomnost_hodin: Optional[float] = Field(default=None, ge=0)


class PayrollPayslipPatch(BaseModel):
    typ_ppv: Optional[str] = Field(default=None, max_length=16)


class PayrollJmhzStatusPatch(BaseModel):
    stav: str = Field(..., max_length=32)
    response_notes: Optional[str] = None
    odeslano_dne: Optional[datetime] = None


def _audit(
    db: Session,
    *,
    current_user: Customer,
    entity_type: str,
    entity_id: int | None,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    write_global_audit_log(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        before_json=before,
        after_json=after,
    )


@router.get("/offices")
def list_offices(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    rows = (
        db.query(PayrollOffice)
        .filter(
            PayrollOffice.tenant_id == int(current_user.tenant_id),
            PayrollOffice.service_id == int(current_user.id),
        )
        .order_by(PayrollOffice.name.asc())
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "vs_cssz": r.vs_cssz,
            "datovka_id": r.datovka_id,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post("/offices")
def create_office(
    body: PayrollOfficeCreate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = PayrollOffice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        name=body.name.strip(),
        vs_cssz=(body.vs_cssz or "").strip() or None,
        datovka_id=(body.datovka_id or "").strip() or None,
        is_active=bool(body.is_active),
    )
    db.add(row)
    db.flush()
    _audit(db, current_user=current_user, entity_type="payroll_office", entity_id=int(row.id), action="create", after={"name": row.name})
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.put("/offices/{office_id}")
def update_office(
    office_id: int,
    body: PayrollOfficeUpdate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = _office_scope(db, current_user, office_id)
    before = {"name": row.name, "vs_cssz": row.vs_cssz, "is_active": row.is_active}
    if body.name is not None:
        row.name = body.name.strip()
    if body.vs_cssz is not None:
        row.vs_cssz = body.vs_cssz.strip() or None
    if body.datovka_id is not None:
        row.datovka_id = body.datovka_id.strip() or None
    if body.is_active is not None:
        row.is_active = bool(body.is_active)
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_office", entity_id=int(row.id), action="update", before=before, after={"name": row.name})
    db.commit()
    return {"ok": True}


@router.delete("/offices/{office_id}")
def deactivate_office(
    office_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = _office_scope(db, current_user, office_id)
    row.is_active = False
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_office", entity_id=int(row.id), action="deactivate")
    db.commit()
    return {"ok": True}


@router.get("/employees")
def list_employees(
    employee_filter: str = Query("all", alias="filter"),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    q = db.query(PayrollEmployee).filter(
        PayrollEmployee.tenant_id == int(current_user.tenant_id),
        PayrollEmployee.service_id == int(current_user.id),
    )
    ef = str(employee_filter or "all").lower()
    if ef == "active":
        q = q.filter(PayrollEmployee.is_active.is_(True))
    elif ef == "inactive":
        q = q.filter(PayrollEmployee.is_active.is_(False))
    rows = q.order_by(PayrollEmployee.last_name.asc(), PayrollEmployee.first_name.asc()).all()

    # aktivní smlouvy = zjednodušeně is_active zaměstnance (plná smluvní vrstva přijde později)
    return {"items": [_employee_snapshot(r, mask=True) for r in rows]}


@router.post("/employees")
def create_employee(
    body: PayrollEmployeeCreate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    ppv = str(body.default_ppv or "hpp").lower()
    if ppv not in PPV_ALLOWED:
        raise HTTPException(status_code=422, detail="Neplatný typ PPV.")
    primary_office_id = None
    if body.primary_office_id:
        _office_scope(db, current_user, int(body.primary_office_id))
        primary_office_id = int(body.primary_office_id)

    emp = PayrollEmployee(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        primary_office_id=primary_office_id,
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        birth_date=body.birth_date,
        birth_number=(body.birth_number or "").strip() or None,
        gender=(body.gender or "").strip() or None,
        street=(body.street or "").strip() or None,
        city=(body.city or "").strip() or None,
        postal_code=(body.postal_code or "").strip() or None,
        country_code=(body.country_code or "").strip() or None,
        email=(body.email or "").strip() or None,
        phone=(body.phone or "").strip() or None,
        tax_residency_country=(body.tax_residency_country or "").strip() or None,
        tax_resident=body.tax_resident,
        education_level=(body.education_level or "").strip() or None,
        oic=(body.oic or "").strip() or None,
        oic_assigned_at=body.oic_assigned_at,
        health_insurance_code=(body.health_insurance_code or "").strip() or None,
        disability_degree=(body.disability_degree or "").strip() or None,
        disability_from=body.disability_from,
        disability_to=body.disability_to,
        ztp_p=bool(body.ztp_p),
        pension_type=(body.pension_type or "").strip() or None,
        pension_from=body.pension_from,
        foreign_national=bool(body.foreign_national),
        citizenship_code=(body.citizenship_code or "").strip() or None,
        id_document_type=(body.id_document_type or "").strip() or None,
        id_document_number=(body.id_document_number or "").strip() or None,
        id_document_issue_country=(body.id_document_issue_country or "").strip() or None,
        residence_permit_until=body.residence_permit_until,
        bank_account=(body.bank_account or "").strip() or None,
        iban=(body.iban or "").strip() or None,
        swift=(body.swift or "").strip() or None,
        contract_hours_per_week=body.contract_hours_per_week,
        hourly_gross_rate=body.hourly_gross_rate,
        default_ppv=ppv,
        is_active=bool(body.is_active),
    )
    db.add(emp)
    db.flush()
    if primary_office_id:
        link = PayrollEmployeeOffice(
            tenant_id=int(current_user.tenant_id),
            employee_id=int(emp.id),
            office_id=primary_office_id,
        )
        db.add(link)
    _audit(db, current_user=current_user, entity_type="payroll_employee", entity_id=int(emp.id), action="create", after={"name": f"{emp.first_name} {emp.last_name}"})
    db.commit()
    db.refresh(emp)
    return {"id": emp.id}


@router.get("/employees/{employee_id}")
def get_employee(
    employee_id: int,
    full_sensitive: bool = Query(False),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    emp = _employee_scope(db, current_user, employee_id)
    return _employee_snapshot(emp, mask=not full_sensitive)


@router.put("/employees/{employee_id}")
def update_employee(
    employee_id: int,
    body: PayrollEmployeeUpdate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    emp = _employee_scope(db, current_user, employee_id)
    before = _employee_snapshot(emp, mask=False)

    data = body.model_dump(exclude_unset=True)
    if "default_ppv" in data and data["default_ppv"]:
        if str(data["default_ppv"]).lower() not in PPV_ALLOWED:
            raise HTTPException(status_code=422, detail="Neplatný typ PPV.")
        emp.default_ppv = str(data["default_ppv"]).lower()
    if "primary_office_id" in data:
        pid = data["primary_office_id"]
        if pid:
            _office_scope(db, current_user, int(pid))
            emp.primary_office_id = int(pid)
            exists = (
                db.query(PayrollEmployeeOffice)
                .filter(
                    PayrollEmployeeOffice.employee_id == emp.id,
                    PayrollEmployeeOffice.office_id == int(pid),
                )
                .first()
            )
            if not exists:
                db.add(
                    PayrollEmployeeOffice(
                        tenant_id=int(current_user.tenant_id),
                        employee_id=int(emp.id),
                        office_id=int(pid),
                    )
                )
        else:
            emp.primary_office_id = None

    for field in (
        "first_name",
        "last_name",
        "birth_number",
        "gender",
        "street",
        "city",
        "postal_code",
        "country_code",
        "email",
        "phone",
        "tax_residency_country",
        "education_level",
        "oic",
        "health_insurance_code",
        "disability_degree",
        "pension_type",
        "citizenship_code",
        "id_document_type",
        "id_document_number",
        "id_document_issue_country",
        "bank_account",
        "iban",
        "swift",
    ):
        if field in data and data[field] is not None:
            val = data[field]
            setattr(emp, field, str(val).strip() if isinstance(val, str) else val)

    for field in ("birth_date", "oic_assigned_at", "disability_from", "disability_to", "pension_from", "residence_permit_until"):
        if field in data:
            setattr(emp, field, data[field])

    for field in ("tax_resident", "ztp_p", "foreign_national", "is_active"):
        if field in data and data[field] is not None:
            setattr(emp, field, bool(data[field]))

    for field in ("contract_hours_per_week", "hourly_gross_rate"):
        if field in data and data[field] is not None:
            setattr(emp, field, float(data[field]))

    if "first_name" in data and data["first_name"]:
        emp.first_name = str(data["first_name"]).strip()
    if "last_name" in data and data["last_name"]:
        emp.last_name = str(data["last_name"]).strip()

    emp.updated_at = datetime.utcnow()
    after = _employee_snapshot(emp, mask=False)
    _audit(db, current_user=current_user, entity_type="payroll_employee", entity_id=int(emp.id), action="update", before=before, after=after)
    db.commit()
    return {"ok": True}


@router.get("/attendance")
def list_attendance(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    rows = (
        db.query(PayrollAttendance)
        .filter(
            PayrollAttendance.tenant_id == int(current_user.tenant_id),
            PayrollAttendance.service_id == int(current_user.id),
            PayrollAttendance.year == year,
            PayrollAttendance.month == month,
        )
        .all()
    )
    emp_map = {e.id: e for e in db.query(PayrollEmployee).filter(PayrollEmployee.service_id == int(current_user.id)).all()}
    out = []
    for r in rows:
        emp = emp_map.get(r.employee_id)
        out.append(
            {
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_label": f"{emp.last_name} {emp.first_name}" if emp else str(r.employee_id),
                "year": r.year,
                "month": r.month,
                "fond_hodin": r.fond_hodin,
                "odpracovano_hodin": r.odpracovano_hodin,
                "dovolena_hodin": r.dovolena_hodin,
                "nemoc_hodin": r.nemoc_hodin,
                "prescas_hodin": r.prescas_hodin,
                "neomluvena_absence_hodin": r.neomluvena_absence_hodin,
                "pritomnost_hodin": r.pritomnost_hodin,
            }
        )
    return {"items": out}


@router.post("/attendance/generate")
def generate_attendance(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    employees = (
        db.query(PayrollEmployee)
        .filter(
            PayrollEmployee.tenant_id == int(current_user.tenant_id),
            PayrollEmployee.service_id == int(current_user.id),
            PayrollEmployee.is_active.is_(True),
        )
        .all()
    )
    created = 0
    for emp in employees:
        exists = (
            db.query(PayrollAttendance)
            .filter(
                PayrollAttendance.employee_id == emp.id,
                PayrollAttendance.year == year,
                PayrollAttendance.month == month,
            )
            .first()
        )
        if exists:
            continue
        weeks = 4.345
        fond = float(emp.contract_hours_per_week or 40) * weeks if emp.contract_hours_per_week else 168.0
        row = PayrollAttendance(
            tenant_id=int(current_user.tenant_id),
            service_id=int(current_user.id),
            employee_id=int(emp.id),
            year=year,
            month=month,
            fond_hodin=fond,
            odpracovano_hodin=0,
            pritomnost_hodin=0,
        )
        db.add(row)
        created += 1
    _audit(db, current_user=current_user, entity_type="payroll_attendance", entity_id=None, action="generate_month", after={"year": year, "month": month, "created": created})
    db.commit()
    return {"created": created}


@router.put("/attendance/{attendance_id}")
def update_attendance(
    attendance_id: int,
    body: PayrollAttendanceUpdate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollAttendance)
        .filter(
            PayrollAttendance.id == attendance_id,
            PayrollAttendance.service_id == int(current_user.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Docházka nenalezena.")
    before = {k: getattr(row, k) for k in ("fond_hodin", "odpracovano_hodin") if hasattr(row, k)}
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, float(v) if v is not None else getattr(row, k))
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_attendance", entity_id=int(row.id), action="update", before=before, after=data)
    db.commit()
    return {"ok": True}


@router.get("/payslips")
def list_payslips(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    rows = (
        db.query(PayrollPayslip)
        .filter(
            PayrollPayslip.service_id == int(current_user.id),
            PayrollPayslip.year == year,
            PayrollPayslip.month == month,
        )
        .all()
    )
    emp_map = {e.id: e for e in db.query(PayrollEmployee).filter(PayrollEmployee.service_id == int(current_user.id)).all()}
    return {
        "items": [
            {
                "id": r.id,
                "employee_id": r.employee_id,
                "employee_label": f"{emp_map[r.employee_id].last_name} {emp_map[r.employee_id].first_name}" if r.employee_id in emp_map else "",
                "year": r.year,
                "month": r.month,
                "typ_ppv": r.typ_ppv,
                "hruba_mzda": r.hruba_mzda,
                "cista_mzda": r.cista_mzda,
                "k_vyplate": r.k_vyplate,
                "naklady_zamestnavatele": r.naklady_zamestnavatele,
                "stav": r.stav,
                "datum_uzavreni": r.datum_uzavreni.isoformat() if r.datum_uzavreni else None,
            }
            for r in rows
        ]
    }


@router.post("/payslips/generate")
def generate_payslips(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    atts = (
        db.query(PayrollAttendance)
        .filter(
            PayrollAttendance.service_id == int(current_user.id),
            PayrollAttendance.year == year,
            PayrollAttendance.month == month,
        )
        .all()
    )
    created = 0
    for att in atts:
        exists = (
            db.query(PayrollPayslip)
            .filter(
                PayrollPayslip.employee_id == att.employee_id,
                PayrollPayslip.year == year,
                PayrollPayslip.month == month,
            )
            .first()
        )
        if exists:
            continue
        emp = _employee_scope(db, current_user, int(att.employee_id))
        slip = PayrollPayslip(
            tenant_id=int(current_user.tenant_id),
            service_id=int(current_user.id),
            employee_id=int(emp.id),
            office_id=emp.primary_office_id,
            attendance_id=int(att.id),
            year=year,
            month=month,
            typ_ppv=emp.default_ppv or "hpp",
            stav="open",
        )
        db.add(slip)
        created += 1
    db.flush()
    _audit(db, current_user=current_user, entity_type="payroll_payslip", entity_id=None, action="generate", after={"year": year, "month": month, "created": created})
    db.commit()
    return {"created": created}


def _recalculate_payslip(db: Session, current_user: Customer, slip: PayrollPayslip) -> None:
    if slip.stav == "closed":
        raise HTTPException(status_code=409, detail="Uzavřený mzdový list nelze přepočítat.")
    att = None
    if slip.attendance_id:
        att = (
            db.query(PayrollAttendance)
            .filter(
                PayrollAttendance.id == slip.attendance_id,
                PayrollAttendance.service_id == int(current_user.id),
            )
            .first()
        )
    if not att:
        att = (
            db.query(PayrollAttendance)
            .filter(
                PayrollAttendance.employee_id == slip.employee_id,
                PayrollAttendance.year == slip.year,
                PayrollAttendance.month == slip.month,
            )
            .first()
        )
    if not att:
        raise HTTPException(status_code=422, detail="Chybí docházka pro přepočet.")
    emp = _employee_scope(db, current_user, int(slip.employee_id))
    gross, soc, health, tax, net, pay, employer = _compute_payout(att, emp)
    slip.hruba_mzda = gross
    slip.social_employee = soc
    slip.health_employee = health
    slip.zalohova_dan = tax
    slip.cista_mzda = net
    slip.k_vyplate = pay
    slip.naklady_zamestnavatele = employer
    slip.attendance_id = int(att.id)
    slip.updated_at = datetime.utcnow()


@router.post("/payslips/{payslip_id}/recalculate")
def recalculate_payslip(
    payslip_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    slip = (
        db.query(PayrollPayslip)
        .filter(PayrollPayslip.id == payslip_id, PayrollPayslip.service_id == int(current_user.id))
        .first()
    )
    if not slip:
        raise HTTPException(status_code=404, detail="Mzdový list nenalezen.")
    before = {"hruba_mzda": slip.hruba_mzda, "cista_mzda": slip.cista_mzda}
    _recalculate_payslip(db, current_user, slip)
    _audit(db, current_user=current_user, entity_type="payroll_payslip", entity_id=int(slip.id), action="recalculate", before=before, after={"hruba_mzda": slip.hruba_mzda})
    db.commit()
    return {"ok": True}


@router.post("/payslips/{payslip_id}/close")
def close_payslip(
    payslip_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    slip = (
        db.query(PayrollPayslip)
        .filter(PayrollPayslip.id == payslip_id, PayrollPayslip.service_id == int(current_user.id))
        .first()
    )
    if not slip:
        raise HTTPException(status_code=404, detail="Mzdový list nenalezen.")
    if slip.stav == "closed":
        raise HTTPException(status_code=409, detail="List je již uzavřený.")
    _recalculate_payslip(db, current_user, slip)
    slip.stav = "closed"
    slip.datum_uzavreni = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_payslip", entity_id=int(slip.id), action="close")
    db.commit()
    return {"ok": True}


@router.put("/payslips/{payslip_id}")
def patch_payslip(
    payslip_id: int,
    body: PayrollPayslipPatch,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    slip = (
        db.query(PayrollPayslip)
        .filter(PayrollPayslip.id == payslip_id, PayrollPayslip.service_id == int(current_user.id))
        .first()
    )
    if not slip:
        raise HTTPException(status_code=404, detail="Mzdový list nenalezen.")
    if slip.stav == "closed":
        raise HTTPException(status_code=409, detail="Uzavřený list nelze měnit.")
    if body.typ_ppv:
        if body.typ_ppv.lower() not in PPV_ALLOWED:
            raise HTTPException(status_code=422, detail="Neplatný typ PPV.")
        slip.typ_ppv = body.typ_ppv.lower()
        slip.updated_at = datetime.utcnow()
        _audit(db, current_user=current_user, entity_type="payroll_payslip", entity_id=int(slip.id), action="update_ppv", after={"typ_ppv": slip.typ_ppv})
        db.commit()
    return {"ok": True}


@router.get("/journal")
def get_journal(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollJournal)
        .filter(
            PayrollJournal.service_id == int(current_user.id),
            PayrollJournal.year == year,
            PayrollJournal.month == month,
        )
        .first()
    )
    if not row:
        closed_cnt = (
            db.query(PayrollPayslip)
            .filter(
                PayrollPayslip.service_id == int(current_user.id),
                PayrollPayslip.year == year,
                PayrollPayslip.month == month,
                PayrollPayslip.stav == "closed",
            )
            .count()
        )
        row = PayrollJournal(
            tenant_id=int(current_user.tenant_id),
            service_id=int(current_user.id),
            year=year,
            month=month,
            zamestnancu_pocet=closed_cnt,
            stav="cekani_na_export",
            payment_order_generated=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return {
        "id": row.id,
        "year": row.year,
        "month": row.month,
        "zamestnancu_pocet": row.zamestnancu_pocet,
        "stav": row.stav,
        "payment_order_generated": row.payment_order_generated,
    }


@router.post("/journal/refresh")
def refresh_journal(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollJournal)
        .filter(
            PayrollJournal.service_id == int(current_user.id),
            PayrollJournal.year == year,
            PayrollJournal.month == month,
        )
        .first()
    )
    if not row:
        row = PayrollJournal(
            tenant_id=int(current_user.tenant_id),
            service_id=int(current_user.id),
            year=year,
            month=month,
        )
        db.add(row)
        db.flush()
    closed_cnt = (
        db.query(PayrollPayslip)
        .filter(
            PayrollPayslip.service_id == int(current_user.id),
            PayrollPayslip.year == year,
            PayrollPayslip.month == month,
            PayrollPayslip.stav == "closed",
        )
        .count()
    )
    row.zamestnancu_pocet = closed_cnt
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_journal", entity_id=int(row.id), action="refresh", after={"closed": closed_cnt})
    db.commit()
    return {"zamestnancu_pocet": closed_cnt}


@router.get("/journal/export-payments")
def export_journal_payments(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    slips = (
        db.query(PayrollPayslip)
        .filter(
            PayrollPayslip.service_id == int(current_user.id),
            PayrollPayslip.year == year,
            PayrollPayslip.month == month,
            PayrollPayslip.stav == "closed",
        )
        .all()
    )
    emps = {e.id: e for e in db.query(PayrollEmployee).filter(PayrollEmployee.service_id == int(current_user.id)).all()}
    buf = StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["employee_id", "name", "iban", "amount_czk", "variable_symbol", "message"])
    for s in slips:
        emp = emps.get(s.employee_id)
        iban = (emp.iban or "").replace(" ", "") if emp else ""
        name = f"{emp.last_name} {emp.first_name}" if emp else ""
        w.writerow([s.employee_id, name, iban, f"{s.k_vyplate:.2f}".replace(".", ","), f"{year}{month:02d}{s.id}", "mzda"])
    data = buf.getvalue().encode("utf-8-sig")
    row = (
        db.query(PayrollJournal)
        .filter(
            PayrollJournal.service_id == int(current_user.id),
            PayrollJournal.year == year,
            PayrollJournal.month == month,
        )
        .first()
    )
    if row:
        row.payment_order_generated = True
        row.stav = "exportovan"
        row.updated_at = datetime.utcnow()
        _audit(db, current_user=current_user, entity_type="payroll_journal", entity_id=int(row.id), action="export_csv")
        db.commit()
    return StreamingResponse(
        BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="payroll_payments_{year}_{month:02d}.csv"'},
    )


@router.get("/jmhz")
def list_jmhz(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    rows = (
        db.query(PayrollJmhzSubmission)
        .filter(PayrollJmhzSubmission.service_id == int(current_user.id))
        .order_by(PayrollJmhzSubmission.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "office_id": r.office_id,
                "year": r.year,
                "month": r.month,
                "typ": r.typ,
                "pocet_zamestnancu": r.pocet_zamestnancu,
                "stav": r.stav,
                "zip_file_path": r.zip_file_path,
                "odeslano_dne": r.odeslano_dne.isoformat() if r.odeslano_dne else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/jmhz")
def create_jmhz(
    office_id: int = Query(..., gt=0),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    typ: str = Query("hlaseni", max_length=32),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    _office_scope(db, current_user, office_id)
    t = str(typ or "hlaseni").lower()
    closed = (
        db.query(PayrollPayslip)
        .filter(
            PayrollPayslip.service_id == int(current_user.id),
            PayrollPayslip.year == year,
            PayrollPayslip.month == month,
            PayrollPayslip.stav == "closed",
            PayrollPayslip.office_id == office_id,
        )
        .count()
    )
    total_closed = (
        db.query(PayrollPayslip)
        .filter(
            PayrollPayslip.service_id == int(current_user.id),
            PayrollPayslip.year == year,
            PayrollPayslip.month == month,
            PayrollPayslip.stav == "closed",
        )
        .count()
    )
    cnt = closed if closed else total_closed
    row = PayrollJmhzSubmission(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        office_id=office_id,
        year=year,
        month=month,
        typ=t,
        pocet_zamestnancu=int(cnt),
        stav="nove",
    )
    db.add(row)
    db.flush()
    _audit(db, current_user=current_user, entity_type="payroll_jmhz", entity_id=int(row.id), action="create")
    db.commit()
    db.refresh(row)
    return {"id": row.id}


@router.post("/jmhz/{submission_id}/build-zip")
def build_jmhz_zip(
    submission_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollJmhzSubmission)
        .filter(PayrollJmhzSubmission.id == submission_id, PayrollJmhzSubmission.service_id == int(current_user.id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Podání nenalezeno.")
    base = Path(DATA_DIR) / "payroll_exports" / str(current_user.tenant_id) / str(current_user.id)
    base.mkdir(parents=True, exist_ok=True)
    fname = f"jmhz_{row.id}_{row.year}_{row.month:02d}.zip"
    fpath = base / fname
    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<JmhzExport xmlns="https://example.invalid/csz-placeholder" generated="{datetime.utcnow().isoformat()}Z">
  <OfficeId>{row.office_id}</OfficeId>
  <Period><Year>{row.year}</Year><Month>{row.month}</Month></Period>
  <Type>{row.typ}</Type>
  <EmployeeCount>{row.pocet_zamestnancu}</EmployeeCount>
  <Note>Placeholder XML — nahraďte generátorem dle specifikace ČSSZ.</Note>
</JmhzExport>
"""
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("jmhz_export.xml", xml_body.encode("utf-8"))
    fpath.write_bytes(bio.getvalue())
    row.zip_file_path = str(fpath.relative_to(Path(DATA_DIR)))
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_jmhz", entity_id=int(row.id), action="build_zip")
    db.commit()
    return {"path": row.zip_file_path}


@router.get("/jmhz/{submission_id}/download")
def download_jmhz(
    submission_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollJmhzSubmission)
        .filter(PayrollJmhzSubmission.id == submission_id, PayrollJmhzSubmission.service_id == int(current_user.id))
        .first()
    )
    if not row or not row.zip_file_path:
        raise HTTPException(status_code=404, detail="Soubor není připraven.")
    path = Path(DATA_DIR) / row.zip_file_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Soubor na disku chybí.")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.patch("/jmhz/{submission_id}/status")
def patch_jmhz_status(
    submission_id: int,
    body: PayrollJmhzStatusPatch,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_payroll_license(db, current_user)
    row = (
        db.query(PayrollJmhzSubmission)
        .filter(PayrollJmhzSubmission.id == submission_id, PayrollJmhzSubmission.service_id == int(current_user.id))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Podání nenalezeno.")
    st = str(body.stav).lower()
    if st not in JMHC_STATES:
        raise HTTPException(status_code=422, detail="Neplatný stav podání.")
    row.stav = st
    if body.response_notes is not None:
        row.response_notes = body.response_notes
    if body.odeslano_dne is not None:
        row.odeslano_dne = body.odeslano_dne
    row.updated_at = datetime.utcnow()
    _audit(db, current_user=current_user, entity_type="payroll_jmhz", entity_id=int(row.id), action="status", after={"stav": st})
    db.commit()
    return {"ok": True}
