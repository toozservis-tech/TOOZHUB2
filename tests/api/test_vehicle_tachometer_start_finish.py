from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle as VehicleModel
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


def _db(tmp_path: Path):
    db_path = tmp_path / "vehicle_tachometer_start_finish.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    return db, engine


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="Tachometer Tenant", license_key="tachometer-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="owner@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Importovane auto",
        vin="TMBJF73T2B9044629",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()
    ensure_vehicle_owner_assignment(db_session, vehicle=vehicle, owner=owner)
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def test_start_and_finish_vehicle_tachometer_flow(tmp_path, monkeypatch) -> None:
    db_session, engine = _db(tmp_path)
    try:
        owner, vehicle = _seed_owned_vehicle(db_session)

        monkeypatch.setattr(
            vehicles_router,
            "create_browser_session",
            lambda **_: SimpleNamespace(
                session_id="browser-session-123",
                captcha_image_data_url="data:image/png;base64,ZmFrZQ==",
                expires_in_seconds=600,
            ),
        )
        monkeypatch.setattr(
            vehicles_router,
            "submit_browser_session",
            lambda **_: """
                <html>
                  <body>
                    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
                    <table>
                      <tbody>
                        <tr>
                          <td>15.05.2025</td>
                          <td>STK</td>
                          <td>CZ-3644-25-05-0162</td>
                          <td>Evidenční kontrola</td>
                          <td>416 588</td>
                          <td>Bez poznámky</td>
                          <td><button>Detail prohlídky</button></td>
                        </tr>
                      </tbody>
                    </table>
                  </body>
                </html>
            """,
        )

        started = vehicles_router.start_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerStartRequest(vin=vehicle.vin),
            current_user=owner,
            db=db_session,
        )
        assert started.session_id == "browser-session-123"
        assert started.captcha_image.startswith("data:image/png;base64,")

        finished = vehicles_router.finish_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerFinishRequest(
                session_id=started.session_id,
                captcha_code="abc12",
            ),
            current_user=owner,
            db=db_session,
        )
        assert finished.latest_mileage_km == 416_588
        assert finished.inspections[0].inspection_kind == "Evidenční kontrola"

        history = vehicles_router.get_vehicle_tachometer_history(
            vehicle_id=vehicle.id,
            current_user=owner,
            db=db_session,
        )
        assert any(item.protocol_number == "CZ-3644-25-05-0162" for item in history)
    finally:
        db_session.close()
        engine.dispose()
