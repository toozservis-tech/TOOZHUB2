"""
Analytics API v1.0 router
Souhrny nákladů a základní statistiky nad service_records.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, ServiceRecord as ServiceRecordModel, Vehicle as VehicleModel
from .auth import can_access_vehicle, get_current_user
from .schemas import (
    AnalyticsCategoryBreakdownOutV1,
    AnalyticsCategoryItemV1,
    AnalyticsMonthlyCostsOutV1,
    AnalyticsMonthlyEntryV1,
    AnalyticsSummaryOutV1,
)

router = APIRouter(prefix="/analytics", tags=["analytics-v1"])


def _normalize_role(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(month_anchor: date, months_delta: int) -> date:
    month_index = (month_anchor.year * 12 + (month_anchor.month - 1)) + int(months_delta)
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _apply_date_filters(
    query,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
):
    if date_from:
        query = query.filter(ServiceRecordModel.performed_at >= datetime.combine(date_from, time.min))
    if date_to:
        end_exclusive = datetime.combine(date_to + timedelta(days=1), time.min)
        query = query.filter(ServiceRecordModel.performed_at < end_exclusive)
    return query


def _build_scoped_query(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: Optional[int],
):
    query = db.query(ServiceRecordModel).join(
        VehicleModel,
        VehicleModel.id == ServiceRecordModel.vehicle_id,
    )

    role_key = _normalize_role(getattr(current_user, "role", None))
    tenant_id = getattr(current_user, "tenant_id", None)

    if vehicle_id is not None:
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        query = query.filter(ServiceRecordModel.vehicle_id == vehicle_id)
        if role_key == "admin" and tenant_id:
            query = query.filter(ServiceRecordModel.tenant_id == tenant_id)
        return query

    if role_key == "user":
        query = query.filter(func.lower(VehicleModel.user_email) == _normalize_email(current_user.email))
        return query

    if role_key in {"service", "developer_admin"}:
        query = query.filter(ServiceRecordModel.user_id == current_user.id)
        return query

    if role_key == "admin" and tenant_id:
        query = query.filter(ServiceRecordModel.tenant_id == tenant_id)
        return query

    return query.filter(ServiceRecordModel.user_id == current_user.id)


@router.get("/summary", response_model=AnalyticsSummaryOutV1)
def get_analytics_summary(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from nesmí být větší než date_to")

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = _apply_date_filters(query, date_from=date_from, date_to=date_to)
    rows = query.all()

    prices = [float(item.price) for item in rows if item.price is not None]
    mileages = [int(item.mileage) for item in rows if item.mileage is not None]
    performed_values = [item.performed_at for item in rows if item.performed_at is not None]

    total_cost = round(sum(prices), 2) if prices else 0.0
    priced_count = len(prices)
    average_cost = round(total_cost / priced_count, 2) if priced_count else None

    return AnalyticsSummaryOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        total_records=len(rows),
        priced_records=priced_count,
        total_cost_czk=total_cost,
        average_cost_czk=average_cost,
        min_cost_czk=(round(min(prices), 2) if prices else None),
        max_cost_czk=(round(max(prices), 2) if prices else None),
        mileage_min=(min(mileages) if mileages else None),
        mileage_max=(max(mileages) if mileages else None),
        latest_service_at=(max(performed_values) if performed_values else None),
    )


@router.get("/categories", response_model=AnalyticsCategoryBreakdownOutV1)
def get_analytics_categories(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from nesmí být větší než date_to")

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = _apply_date_filters(query, date_from=date_from, date_to=date_to)
    rows = query.all()

    buckets: dict[str, dict[str, object]] = {}
    for item in rows:
        category = str(item.category or "").strip() or "NEZARAZENO"
        bucket = buckets.setdefault(
            category,
            {
                "records_count": 0,
                "priced_records_count": 0,
                "total_cost_czk": 0.0,
                "latest_service_at": None,
            },
        )
        bucket["records_count"] = int(bucket["records_count"]) + 1

        if item.price is not None:
            bucket["priced_records_count"] = int(bucket["priced_records_count"]) + 1
            bucket["total_cost_czk"] = float(bucket["total_cost_czk"]) + float(item.price)

        latest_value = bucket["latest_service_at"]
        if item.performed_at and (latest_value is None or item.performed_at > latest_value):
            bucket["latest_service_at"] = item.performed_at

    items = []
    for category, bucket in buckets.items():
        priced_records_count = int(bucket["priced_records_count"])
        total_cost = round(float(bucket["total_cost_czk"]), 2)
        items.append(
            AnalyticsCategoryItemV1(
                category=category,
                records_count=int(bucket["records_count"]),
                priced_records_count=priced_records_count,
                total_cost_czk=total_cost,
                average_cost_czk=(
                    round(total_cost / priced_records_count, 2) if priced_records_count else None
                ),
                latest_service_at=bucket["latest_service_at"],
            )
        )

    items.sort(key=lambda row: (-row.total_cost_czk, -row.records_count, row.category))

    return AnalyticsCategoryBreakdownOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        total_records=len(rows),
        categories=items,
    )


@router.get("/monthly-costs", response_model=AnalyticsMonthlyCostsOutV1)
def get_analytics_monthly_costs(
    months: int = Query(default=12, ge=1, le=36),
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month_count = int(months)
    today = date.today()
    last_month = _month_start(today)
    first_month = _add_months(last_month, -(month_count - 1))
    end_exclusive = _add_months(last_month, 1)

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = query.filter(
        ServiceRecordModel.performed_at >= datetime.combine(first_month, time.min),
        ServiceRecordModel.performed_at < datetime.combine(end_exclusive, time.min),
    )
    rows = query.all()

    entries_map: dict[str, dict[str, object]] = {}
    for offset in range(month_count):
        month_value = _add_months(first_month, offset)
        month_key = f"{month_value.year:04d}-{month_value.month:02d}"
        entries_map[month_key] = {
            "month": month_key,
            "label": f"{month_value.month:02d}/{month_value.year}",
            "records_count": 0,
            "priced_records_count": 0,
            "total_cost_czk": 0.0,
        }

    for item in rows:
        source_dt = item.performed_at or item.created_at
        if source_dt is None:
            continue

        month_key = f"{source_dt.year:04d}-{source_dt.month:02d}"
        bucket = entries_map.get(month_key)
        if not bucket:
            continue

        bucket["records_count"] = int(bucket["records_count"]) + 1
        if item.price is not None:
            bucket["priced_records_count"] = int(bucket["priced_records_count"]) + 1
            bucket["total_cost_czk"] = float(bucket["total_cost_czk"]) + float(item.price)

    entries = [
        AnalyticsMonthlyEntryV1(
            month=payload["month"],
            label=payload["label"],
            records_count=int(payload["records_count"]),
            priced_records_count=int(payload["priced_records_count"]),
            total_cost_czk=round(float(payload["total_cost_czk"]), 2),
        )
        for payload in entries_map.values()
    ]

    total_records = sum(item.records_count for item in entries)
    priced_records = sum(item.priced_records_count for item in entries)
    total_cost = round(sum(item.total_cost_czk for item in entries), 2)

    return AnalyticsMonthlyCostsOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        months=month_count,
        generated_at=datetime.utcnow(),
        total_records=total_records,
        priced_records=priced_records,
        total_cost_czk=total_cost,
        entries=entries,
    )
