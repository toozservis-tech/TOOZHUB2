"""Exercise the composed v1 router, including its dynamic reminder routes."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Reminder, Tenant
from src.modules.vehicle_hub.routers_v1 import api_router
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture()
def context(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.sqlite'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    users = []
    for number in (1, 2):
        tenant = Tenant(name=f"Settings fixture {number}", license_key=f"settings-fixture-{number}")
        db.add(tenant)
        db.flush()
        user = Customer(tenant_id=tenant.id, email=f"settings-{number}@example.invalid", role="user")
        db.add(user)
        db.flush()
        users.append(user)
    reminder = Reminder(customer_id=users[0].id, tenant_id=users[0].tenant_id,
                        type="VLASTNI", text="Synthetic reminder", is_manual=True)
    db.add(reminder)
    db.commit()
    clients = []
    for user in users:
        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = (lambda selected: lambda: selected)(user)
        clients.append(TestClient(app))
    try:
        yield db, users, clients, reminder
    finally:
        for client in clients:
            client.close()
        db.close()
        engine.dispose()


def test_settings_put_reaches_settings_handler_and_round_trips(context):
    db, users, clients, reminder = context
    response = clients[0].put("/api/v1/reminders/settings", json={
        "notification": {"notification_method": "app", "notify_days_before": 3}})
    assert response.status_code == 200, response.text
    assert response.json()["notification"] == {"notification_method": "app", "notify_days_before": 3}
    assert clients[0].get("/api/v1/reminders/settings").json() == response.json()
    db.refresh(users[0])
    assert json.loads(users[0].reminder_settings)["notification"]["notify_days_before"] == 3
    db.refresh(reminder)
    assert reminder.text == "Synthetic reminder"


def test_settings_save_is_scoped_to_current_account(context):
    db, users, clients, _ = context
    response = clients[0].put("/api/v1/reminders/settings", json={"enabled": False})
    assert response.status_code == 200
    assert clients[0].get("/api/v1/reminders/settings").json()["enabled"] is False
    assert clients[1].get("/api/v1/reminders/settings").json()["enabled"] is True
    db.refresh(users[1])
    assert users[1].reminder_settings is None


def test_numeric_reminder_put_still_updates_only_owned_reminder(context):
    db, users, clients, reminder = context
    path = f"/api/v1/reminders/{reminder.id}"
    assert clients[1].put(path, json={"text": "Foreign edit"}).status_code == 404
    response = clients[0].put(path, json={"text": "Own edit", "is_completed": True})
    assert response.status_code == 200, response.text
    assert response.json()["is_completed"] is True
    db.refresh(reminder)
    assert reminder.text == "Own edit"
    db.refresh(users[0])
    assert users[0].reminder_settings is None
