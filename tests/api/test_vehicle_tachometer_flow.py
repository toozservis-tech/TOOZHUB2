from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import requests
import base64
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceRecord, Tenant, Vehicle as VehicleModel
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


CAPTCHA_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg==")

START_HTML = """
<html>
  <body>
    <form action="/Home/Search" method="post">
      <input name="__RequestVerificationToken" type="hidden" value="token-123" />
      <img id="captcha_IMG" src="/Home/CaptchaPartial" />
    </form>
  </body>
</html>
"""

RESULT_HTML = """
<html>
  <body>
    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
    <table>
      <thead>
        <tr>
          <th>Datum prohlídky</th>
          <th>Prohlídka</th>
          <th>Číslo protokolu</th>
          <th>Druh prohlídky</th>
          <th>Stav km</th>
          <th>Poznámka</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>15.05.2025</td>
          <td>STK</td>
          <td>CZ-3644-25-05-0162</td>
          <td>Evidenční kontrola</td>
          <td>416 588</td>
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
        <tr>
          <td>22.04.2024</td>
          <td>STK</td>
          <td>CZ-3316-24-04-1239</td>
          <td>Pravidelná</td>
          <td>402 411</td>
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

RESULT_HTML_WITH_INLINE_DETAIL = """
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
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
        <tr class="inspection-detail">
          <td colspan="7">
            <div class="detail-card">
              <h3>Detail prohlídky</h3>
              <p>Zjištěné závady</p>
              <ul>
                <li>B - Netěsnost motoru</li>
                <li>A - Koroze výfuku</li>
              </ul>
              <a href="/protocols/CZ-3644-25-05-0162.pdf">PDF protokol</a>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

RESULT_HTML_WITH_DETAIL_FORM = """
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
          <td></td>
          <td>
            <form action="/Home/InspectionDetail" method="post">
              <input type="hidden" name="protocolId" value="CZ-3644-25-05-0162" />
              <button type="submit">Detail prohlídky</button>
            </form>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

DETAIL_HTML_WITH_FINDINGS = """
<html>
  <body>
    <div class="inspection-detail-body">
      <h3>Detail prohlídky</h3>
      <p>Zjištěné závady</p>
      <ul>
        <li>C - Vážná závada brzdového potrubí</li>
      </ul>
    </div>
  </body>
</html>
"""


class _FakeResponse(requests.Response):
    def __init__(self, text: str = "", content: bytes = b"", status_code: int = 200, headers: dict | None = None):
        super().__init__()
        self._content = content or text.encode("utf-8")
        self._content_consumed = True
        self.encoding = "utf-8"
        self.status_code = status_code
        self.headers.update(headers or {})


class _FakeSession:
    last_post_data: dict | None = None

    def __init__(self):
        self.headers = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.cookies.set("sessionid", "cookie-123")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        if url.rstrip("/").endswith("www.kontrolatachometru.cz"):
            return _FakeResponse(text=START_HTML, status_code=200)
        if url.endswith("/Home/CaptchaPartial"):
            return _FakeResponse(
                content=CAPTCHA_PNG,
                status_code=200,
                headers={"Content-Type": "image/png"},
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    def post(self, url: str, data: dict | None = None, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        _FakeSession.last_post_data = dict(data or {})
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text=RESULT_HTML, status_code=200)


class _FakeSessionHtml500(_FakeSession):
    def post(self, url: str, data: dict | None = None, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        _FakeSession.last_post_data = dict(data or {})
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text="<!DOCTYPE html><html><body>Server Error</body></html>", status_code=500)


class _FakeSessionNoResults(_FakeSession):
    def post(self, url: str, data: dict | None = None, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        _FakeSession.last_post_data = dict(data or {})
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text="<html><body>Bez tabulky</body></html>", status_code=200)


class _FakeSessionInlineDetail(_FakeSession):
    def post(self, url: str, data: dict | None = None, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        _FakeSession.last_post_data = dict(data or {})
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text=RESULT_HTML_WITH_INLINE_DETAIL, status_code=200)


class _FakeSessionDetailForm(_FakeSession):
    def post(self, url: str, data: dict | None = None, timeout: int = 20, *, allow_redirects=False, stream=True, hooks=None):
        _FakeSession.last_post_data = dict(data or {})
        if url.endswith("/Home/Search"):
            return _FakeResponse(text=RESULT_HTML_WITH_DETAIL_FORM, status_code=200)
        if url.endswith("/Home/InspectionDetail"):
            return _FakeResponse(text=DETAIL_HTML_WITH_FINDINGS, status_code=200)
        raise AssertionError(f"Unexpected POST url: {url}")


@pytest.fixture(autouse=True)
def _clear_tachometer_store():
    vehicles_router._TACHOMETER_CHALLENGE_STORE.clear()
    yield
    vehicles_router._TACHOMETER_CHALLENGE_STORE.clear()


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_tachometer.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="Tachometer Tenant", license_key="tachometer-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="driver@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email="legacy@example.com",
        nickname="Kontrolované auto",
        vin="TMBJF73T2B9044629",
        stk_valid_until=date(2030, 1, 1),
        current_mileage_km=410_000,
        last_stk_mileage_km=402_411,
    )
    db_session.add(vehicle)
    db_session.flush()

    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def test_init_vehicle_tachometer_returns_captcha_for_owned_vehicle(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSession)

    response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert response.session_id
    assert response.captcha_image_base64
    stored = vehicles_router._TACHOMETER_CHALLENGE_STORE[response.session_id]
    assert stored["vehicle_id"] == vehicle.id
    assert stored["expected_vin"] == "TMBJF73T2B9044629"


def test_submit_vehicle_tachometer_updates_vehicle_and_creates_audit_record(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSession)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    response = vehicles_router.submit_vehicle_tachometer(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleTachometerSubmitRequest(
            session_id=init_response.session_id,
            captcha_code="2ukkq",
        ),
        current_user=owner,
        db=db_session,
    )

    db_session.refresh(vehicle)
    assert _FakeSession.last_post_data is not None
    assert _FakeSession.last_post_data["VIN"] == "TMBJF73T2B9044629"
    assert _FakeSession.last_post_data["captcha$TB"] == "2ukkq"
    assert response.latest_mileage_km == 416_588
    assert response.vehicle.last_stk_mileage_km == 416_588
    assert response.vehicle.current_mileage_km == 416_588
    assert vehicle.last_stk_mileage_km == 416_588
    assert vehicle.current_mileage_km == 416_588
    assert response.inspections[0].protocol_number == "CZ-3644-25-05-0162"

    history_record = (
        db_session.query(ServiceRecord)
        .filter(ServiceRecord.id == response.created_record_id)
        .first()
    )
    assert history_record is not None
    assert history_record.description == "Načteno z kontroly tachometru (MDČR)"
    assert history_record.mileage == 416_588
    assert "kontrolatachometru.cz" in (history_record.note or "")

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    assert len(history) == 2
    assert [item.mileage_km for item in history] == [402_411, 416_588]
    assert history[0].id > 0
    assert history[0].mileage_km == 402_411
    assert history[1].protocol_number == "CZ-3644-25-05-0162"
    assert history[1].inspection_type == "STK / Evidenční kontrola"
    assert history[1].source == "kontrolatachometru.cz"
    assert history[1].status == "imported"
    assert history[1].summary
    assert history[1].detail_available is False
    assert history[1].has_documents is False
    assert history[1].documents_count == 0
    assert len(history[1].documents) == 1
    assert history[1].documents[0].available is False
    assert history[1].source_detail_reference == {"kind": "button_label", "label": "Detail prohlídky"}
    assert history[0].is_monotonic_valid is True
    assert history[1].is_monotonic_valid is True

    detail = vehicles_router.get_vehicle_tachometer_history_entry_detail(
        vehicle_id=vehicle.id,
        entry_id=history[1].id,
        current_user=owner,
        db=db_session,
    )
    assert detail.protocol_number == "CZ-3644-25-05-0162"
    assert len(detail.documents) == 1
    assert detail.documents[0].available is False
    assert "není dostupný v uložených datech" in str(detail.documents[0].reason)

    documents = vehicles_router.get_vehicle_tachometer_history_entry_documents(
        vehicle_id=vehicle.id,
        entry_id=history[1].id,
        current_user=owner,
        db=db_session,
    )
    assert len(documents) == 1
    assert documents[0].open_mode == "unavailable"


def test_parse_tachometer_inspections_extracts_inline_detail_and_documents() -> None:
    inspections = vehicles_router._parse_tachometer_inspections(RESULT_HTML_WITH_INLINE_DETAIL)

    assert len(inspections) == 1
    assert inspections[0].protocol_number == "CZ-3644-25-05-0162"
    assert inspections[0].detail_available is True
    assert inspections[0].findings_summary == "B - Netěsnost motoru • A - Koroze výfuku"
    assert inspections[0].findings_items == ["B - Netěsnost motoru", "A - Koroze výfuku"]
    assert inspections[0].documents[0]["available"] is True
    assert inspections[0].documents[0]["external_url"] == "https://www.kontrolatachometru.cz/protocols/CZ-3644-25-05-0162.pdf"


def test_history_endpoint_returns_detail_available_without_document(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionDetailForm)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    vehicles_router.submit_vehicle_tachometer(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleTachometerSubmitRequest(
            session_id=init_response.session_id,
            captcha_code="2ukkq",
        ),
        current_user=owner,
        db=db_session,
    )

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    detail = vehicles_router.get_vehicle_tachometer_history_entry_detail(
        vehicle_id=vehicle.id,
        entry_id=history[-1].id,
        current_user=owner,
        db=db_session,
    )

    assert detail.detail_available is True
    assert detail.findings_summary == "C - Vážná závada brzdového potrubí"
    assert detail.findings_items == ["C - Vážná závada brzdového potrubí"]
    assert detail.has_documents is False
    assert len(detail.documents) == 1
    assert detail.documents[0].available is False
    assert "detail kontroly" in str(detail.documents[0].reason).lower()


def test_tachometer_history_deduplicates_near_duplicates_and_prefers_higher_km(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    imported_at = datetime(2026, 1, 10, 10, 0)
    duplicate_low = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_410,
        protocol_number="CZ-LOW",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Nižší km",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    duplicate_high = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_411,
        protocol_number="CZ-HIGH",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Vyšší km",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    db_session.add_all([duplicate_low, duplicate_high])
    db_session.commit()

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert len(history) == 1
    assert history[0].mileage_km == 402_411
    assert history[0].merged_duplicate_count == 1
    assert sorted(history[0].merged_entry_ids) == sorted([duplicate_low.id, duplicate_high.id])
    assert history[0].merge_reason is not None


def test_tachometer_history_marks_km_decrease_as_anomaly(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    imported_at = datetime(2026, 1, 10, 10, 0)
    older = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_411,
        protocol_number="CZ-1",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Older",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    decreased = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2025, 5, 15, 8, 0),
        mileage_km=402_410,
        protocol_number="CZ-2",
        inspection_type="STK / Evidenční kontrola",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Decreased",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    later = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2026, 5, 15, 8, 0),
        mileage_km=416_588,
        protocol_number="CZ-3",
        inspection_type="STK / Evidenční kontrola",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Later",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    db_session.add_all([older, decreased, later])
    db_session.commit()

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert [item.mileage_km for item in history] == [402_411, 402_410, 416_588]
    assert history[0].anomaly is False
    assert history[1].anomaly is True
    assert history[1].anomaly_type == "km_decrease"
    assert history[1].anomaly_delta_km == -1
    assert history[1].is_monotonic_valid is False
    assert history[2].anomaly is False


def test_tachometer_history_output_is_stable_and_deterministic(db_session) -> None:
    imported_at = datetime(2026, 1, 10, 10, 0)
    tenant = Tenant(name="Stable Tenant", license_key="stable-tenant-key")
    db_session.add(tenant)
    db_session.flush()
    owner = Customer(
        tenant_id=tenant.id,
        email="stable@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()
    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Stable Car",
        vin="TMBJF73T2B9044630",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()
    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    db_session.add_all([
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2025, 5, 15, 8, 0),
            mileage_km=416_588,
            protocol_number="CZ-3",
            inspection_type="C",
            source="kontrolatachometru.cz",
            status="imported",
            summary="3",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2024, 4, 22, 8, 0),
            mileage_km=402_411,
            protocol_number="CZ-1",
            inspection_type="A",
            source="kontrolatachometru.cz",
            status="imported",
            summary="1",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2024, 4, 22, 8, 0),
            mileage_km=402_410,
            protocol_number="CZ-2",
            inspection_type="B",
            source="kontrolatachometru.cz",
            status="imported",
            summary="2",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
    ])
    db_session.commit()

    first = vehicles_router.get_vehicle_tachometer_history(vehicle_id=vehicle.id, current_user=owner, db=db_session)
    second = vehicles_router.get_vehicle_tachometer_history(vehicle_id=vehicle.id, current_user=owner, db=db_session)

    assert [(item.id, item.mileage_km, item.merged_duplicate_count) for item in first] == [
        (item.id, item.mileage_km, item.merged_duplicate_count) for item in second
    ]


def test_submit_vehicle_tachometer_returns_friendly_expired_message_for_html_500(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionHtml500)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.submit_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerSubmitRequest(
                session_id=init_response.session_id,
                captcha_code="2ukkq",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 410
    assert "Captcha session vypršela nebo je neplatná" in str(exc.value.detail)


def test_submit_vehicle_tachometer_returns_not_found_when_no_rows_exist(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionNoResults)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.submit_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerSubmitRequest(
                session_id=init_response.session_id,
                captcha_code="2ukkq",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 404
    assert "nebyly nalezeny žádné údaje STK/emisí" in str(exc.value.detail)


@pytest.mark.parametrize('url', [
    'https://www.kontrolatachometru.cz.evil.invalid/a',
    'https://www.kontrolatachometru.cz@evil.invalid/a',
    'https://user:password@www.kontrolatachometru.cz/a',
    'https://www.kontrolatachometru.cz:8443/a',
    'https://www.kontrolatachometru.cz:bad/a',
    'https://www.kontrolatachometru.cz./a',
    'http://www.kontrolatachometru.cz/a', 'http://127.0.0.1/private',
    '//evil.invalid/a', 'file:///etc/passwd', 'javascript:alert(1)',
    'https://www.kontrolatachometru.cz\\@evil.invalid/a',
    '/Home/one\ntwo', 'https://[broken/a',
])
def test_tachometer_rejects_non_official_origin(url):
    assert vehicles_router._same_origin_external_url(url) is None


@pytest.mark.parametrize('url', ['/protocol.pdf?x=1&amp;y=2', 'https://WWW.KONTROLATACHOMETRU.CZ:443/protocol.pdf?x=1&y=2'])
def test_tachometer_canonicalises_official_links(url):
    assert vehicles_router._same_origin_external_url(url) == 'https://www.kontrolatachometru.cz/protocol.pdf?x=1&y=2'


class _RedirectSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def get(self, url, **kwargs):
        return self._request('GET', url, kwargs)
    def post(self, url, **kwargs):
        return self._request('POST', url, kwargs)
    def _request(self, method, url, kwargs):
        assert kwargs['allow_redirects'] is False
        assert kwargs['stream'] is True
        self.calls.append((method, url, kwargs.get('data')))
        return next(self.responses)


@pytest.mark.parametrize('target', [
    'https://www.kontrolatachometru.cz.evil.invalid/collect',
    'https://www.kontrolatachometru.cz@evil.invalid/collect',
    'https://www.kontrolatachometru.cz:8443/collect',
    'http://www.kontrolatachometru.cz/collect', '//127.0.0.1/private',
    'https://[malformed/collect',
])
def test_redirect_cannot_forward_vin_token_or_captcha(target):
    session = _RedirectSession([_FakeResponse(status_code=307, headers={'Location': target})])
    with pytest.raises(requests.RequestException):
        vehicles_router._tachometer_request(session, 'POST', vehicles_router.TACHOMETER_BASE_URL + '/Home/Search',
                                             data={'VIN': 'SYNTHETIC', 'captcha$TB': 'fixture'})
    assert len(session.calls) == 1


@pytest.mark.parametrize('status,method,preserve', [(307,'POST',True), (308,'POST',True), (302,'GET',False), (303,'GET',False)])
def test_same_origin_redirect_preserves_only_appropriate_body(status, method, preserve):
    session = _RedirectSession([_FakeResponse(status_code=status, headers={'Location': '/Home/Result'}), _FakeResponse(text=RESULT_HTML)])
    body = {'VIN': 'SYNTHETIC', '__RequestVerificationToken': 'fixture'}
    response = vehicles_router._tachometer_request(session, 'POST', vehicles_router.TACHOMETER_BASE_URL + '/Home/Search', data=body)
    assert response.text == RESULT_HTML
    assert session.calls[-1] == (method, vehicles_router.TACHOMETER_BASE_URL + '/Home/Result', body if preserve else None)


def test_redirect_loop_and_streamed_size_are_bounded():
    session = _RedirectSession([_FakeResponse(status_code=302, headers={'Location': '/loop'}) for _ in range(4)])
    with pytest.raises(requests.RequestException):
        vehicles_router._tachometer_request(session, 'GET', '/loop')
    assert len(session.calls) == 4
    session = _RedirectSession([_FakeResponse(content=b'x' * 200_000, headers={'Content-Length': '1'})])
    with pytest.raises(requests.RequestException):
        vehicles_router._tachometer_request(session, 'GET', '/image', max_bytes=100_000)


@pytest.mark.parametrize('content', [b'<html>private</html>', b'<svg onload="alert(1)"/>', b'not an image', CAPTCHA_PNG[:40]])
def test_non_raster_or_corrupt_captcha_is_not_relayed(content):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        vehicles_router._captcha_mime_type(content)
    assert denied.value.status_code == 502
    assert content.decode('utf-8', errors='ignore') not in denied.value.detail


def test_captcha_mime_is_detected_from_actual_content():
    assert vehicles_router._captcha_mime_type(CAPTCHA_PNG) == 'image/png'


def _fixture_challenge(monkeypatch, *, customer_id=17, vehicle_id=None):
    monkeypatch.setattr(vehicles_router.requests, 'Session', _FakeSession)
    return vehicles_router._create_tachometer_session(expected_vin='TMBJF73T2B9044629', vehicle_id=vehicle_id, customer_id=customer_id)


def test_challenge_cannot_be_used_by_different_customer_or_vehicle(monkeypatch):
    from fastapi import HTTPException
    challenge = _fixture_challenge(monkeypatch, vehicle_id=51)
    for customer, vehicle, vin, status in [(18,51,'TMBJF73T2B9044629',410), (17,52,'TMBJF73T2B9044629',409),
                                          (17,None,'TMBJF73T2B9044629',409), (17,51,'OTHER',409)]:
        with pytest.raises(HTTPException) as denied:
            vehicles_router._lookup_tachometer_with_session(session_id=challenge.session_id, vin=vin,
                captcha_code='fixture', customer_id=customer, vehicle_id=vehicle)
        assert denied.value.status_code == status
        assert challenge.session_id in vehicles_router._TACHOMETER_CHALLENGE_STORE
    result = vehicles_router._lookup_tachometer_with_session(session_id=challenge.session_id,
        vin='TMBJF73T2B9044629', captcha_code='fixture', customer_id=17, vehicle_id=51)
    assert result.latest_mileage_km == 416588
    with pytest.raises(HTTPException) as replay:
        vehicles_router._lookup_tachometer_with_session(session_id=challenge.session_id,
            vin='TMBJF73T2B9044629', captcha_code='fixture', customer_id=17, vehicle_id=51)
    assert replay.value.status_code == 410


def test_simultaneous_lookup_only_contacts_provider_once(monkeypatch):
    from fastapi import HTTPException
    from concurrent.futures import ThreadPoolExecutor
    import threading
    challenge = _fixture_challenge(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    class Blocking(_FakeSession):
        calls = 0
        def post(self, *args, **kwargs):
            Blocking.calls += 1
            entered.set()
            assert release.wait(5)
            return super().post(*args, **kwargs)
    monkeypatch.setattr(vehicles_router.requests, 'Session', Blocking)
    args = dict(session_id=challenge.session_id, vin='TMBJF73T2B9044629', captcha_code='fixture', customer_id=17)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(vehicles_router._lookup_tachometer_with_session, **args)
        try:
            assert entered.wait(5)
            with pytest.raises(HTTPException) as busy:
                vehicles_router._lookup_tachometer_with_session(**args)
            assert busy.value.status_code == 409
        finally:
            release.set()
        assert running.result().latest_mileage_km == 416588
    assert Blocking.calls == 1


def test_wrong_captcha_can_retry_without_consuming_other_challenges(monkeypatch):
    from fastapi import HTTPException
    challenge = _fixture_challenge(monkeypatch)
    other = _fixture_challenge(monkeypatch, customer_id=18)
    class WrongOnce(_FakeSession):
        calls = 0
        def post(self, *args, **kwargs):
            WrongOnce.calls += 1
            if WrongOnce.calls == 1:
                return _FakeResponse(text=vehicles_router._TACHOMETER_CAPTCHA_ERROR_TEXT)
            return super().post(*args, **kwargs)
    monkeypatch.setattr(vehicles_router.requests, 'Session', WrongOnce)
    args = dict(session_id=challenge.session_id, vin='TMBJF73T2B9044629', captcha_code='fixture', customer_id=17)
    with pytest.raises(HTTPException) as wrong:
        vehicles_router._lookup_tachometer_with_session(**args)
    assert wrong.value.status_code == 422
    assert vehicles_router._lookup_tachometer_with_session(**args).latest_mileage_km == 416588
    assert other.session_id in vehicles_router._TACHOMETER_CHALLENGE_STORE


def test_failed_creation_frees_capacity_and_does_not_expose_provider_error(monkeypatch, capsys):
    from fastapi import HTTPException
    marker = 'PRIVATE_PROVIDER_TOKEN'
    class Failed(_FakeSession):
        def get(self, *args, **kwargs):
            raise requests.ConnectionError('https://user:' + marker + '@invalid.test?VIN=private')
    monkeypatch.setattr(vehicles_router.requests, 'Session', Failed)
    with pytest.raises(HTTPException) as unavailable:
        vehicles_router._create_tachometer_session(expected_vin=None, vehicle_id=None, customer_id=17)
    assert unavailable.value.status_code == 502
    assert marker not in unavailable.value.detail
    assert marker not in capsys.readouterr().out
    assert vehicles_router._TACHOMETER_CHALLENGE_STORE == {}


def test_challenge_capacity_is_per_customer_and_globally_bounded(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(vehicles_router, '_TACHOMETER_MAX_CHALLENGES_PER_CUSTOMER', 2)
    monkeypatch.setattr(vehicles_router, '_TACHOMETER_MAX_CHALLENGES', 3)
    _fixture_challenge(monkeypatch)
    _fixture_challenge(monkeypatch)
    with pytest.raises(HTTPException) as limit:
        _fixture_challenge(monkeypatch)
    assert limit.value.status_code == 429
    _fixture_challenge(monkeypatch, customer_id=18)
    with pytest.raises(HTTPException) as global_limit:
        _fixture_challenge(monkeypatch, customer_id=19)
    assert global_limit.value.status_code == 429
    assert len(vehicles_router._TACHOMETER_CHALLENGE_STORE) == 3


def test_repeated_import_reuses_record_and_history(db_session, monkeypatch):
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, 'Session', _FakeSession)
    ids = []
    for _ in range(2):
        challenge = vehicles_router.init_vehicle_tachometer(vehicle.id, owner, db_session)
        result = vehicles_router.submit_vehicle_tachometer(vehicle.id,
            vehicles_router.VehicleTachometerSubmitRequest(session_id=challenge.session_id, captcha_code='fixture'), owner, db_session)
        ids.append(result.created_record_id)
    assert ids[0] == ids[1]
    assert db_session.query(ServiceRecord).count() == 1
    assert db_session.query(vehicles_router.VehicleTachometerHistoryEntryModel).count() == 2


def test_import_checks_access_again_after_provider_response(db_session, monkeypatch):
    from fastapi import HTTPException
    owner, vehicle = _seed_owned_vehicle(db_session)
    lookup = vehicles_router.TachometerLookupResponse(vin=vehicle.vin, latest_mileage_km=416588,
        latest_check_date=None, inspections=vehicles_router._parse_tachometer_inspections(RESULT_HTML))
    monkeypatch.setattr(vehicles_router, 'can_access_vehicle', lambda *args: False)
    with pytest.raises(HTTPException) as denied:
        vehicles_router._store_tachometer_mileage_result(vehicle=vehicle, lookup=lookup, current_user=owner, db=db_session)
    assert denied.value.status_code == 403
    assert db_session.query(ServiceRecord).count() == 0
    assert vehicle.current_mileage_km == 410000


def test_import_does_not_apply_data_after_vin_changed(db_session):
    from fastapi import HTTPException
    owner, vehicle = _seed_owned_vehicle(db_session)
    lookup = vehicles_router.TachometerLookupResponse(vin='OTHER_VIN', latest_mileage_km=416588,
        latest_check_date=None, inspections=vehicles_router._parse_tachometer_inspections(RESULT_HTML))
    with pytest.raises(HTTPException) as denied:
        vehicles_router._store_tachometer_mileage_result(vehicle=vehicle, lookup=lookup, current_user=owner, db=db_session)
    assert denied.value.status_code == 409
    assert db_session.query(ServiceRecord).count() == 0
    assert vehicle.current_mileage_km == 410000


def test_unknown_inspection_date_is_still_idempotent(db_session):
    owner, vehicle = _seed_owned_vehicle(db_session)
    lookup = vehicles_router.TachometerLookupResponse(vin=vehicle.vin, latest_mileage_km=416588,
        latest_check_date=None, inspections=[vehicles_router.TachometerInspectionOut(mileage_km=416588, protocol_number='UNKNOWN-DATE')])
    ids = []
    for _ in range(2):
        _, record_id = vehicles_router._store_tachometer_mileage_result(vehicle=vehicle, lookup=lookup, current_user=owner, db=db_session)
        ids.append(record_id)
    assert ids[0] == ids[1]
    assert db_session.query(ServiceRecord).count() == 1
    assert db_session.query(vehicles_router.VehicleTachometerHistoryEntryModel).count() == 1


@pytest.mark.parametrize('oversized', [False, True])
def test_requests_transport_checks_redirect_before_following_and_bounds_its_body(oversized):
    """Use the real requests Session redirect machinery; the adapter contains no network."""
    from io import BytesIO
    from requests.adapters import BaseAdapter
    class FixtureRaw(BytesIO):
        released = False
        def release_conn(self):
            self.released = True
    class FixtureAdapter(BaseAdapter):
        calls = []
        last_raw = None
        def send(self, request, **kwargs):
            self.calls.append(request)
            response = requests.Response()
            response.status_code = 307
            response.request = request
            response.url = request.url
            response.headers['Location'] = 'https://www.kontrolatachometru.cz.evil.invalid/collect'
            response.headers['Content-Length'] = '1'
            self.last_raw = FixtureRaw(b'x' * (100_000 if oversized else 1))
            response.raw = self.last_raw
            return response
        def close(self):
            pass
    with requests.Session() as session:
        session.trust_env = False
        adapter = FixtureAdapter()
        session.mount('https://', adapter)
        with pytest.raises(requests.RequestException) as rejected:
            vehicles_router._tachometer_request(session, 'POST', '/Home/Search',
                data={'VIN': 'fixture', 'captcha$TB': 'synthetic'}, max_bytes=2000)
        assert ('exceeds limit' if oversized else 'Invalid tachometer redirect') in str(rejected.value)
        assert len(adapter.calls) == 1
        assert adapter.calls[0].url == vehicles_router.TACHOMETER_BASE_URL + '/Home/Search'
        assert adapter.last_raw.closed or adapter.last_raw.released


@pytest.mark.parametrize('expiry', [date(2028, 2, 29), date(2024, 4, 22)])
def test_mileage_import_also_persists_explicit_registry_expiry(db_session, monkeypatch, expiry):
    from src.modules.vehicle_hub.decoder.inspection_validity import InspectionValidity
    import json
    from src.modules.vehicle_hub.models import VehicleTachometerHistoryEntry
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, 'Session', _FakeSession)
    monkeypatch.setattr(vehicles_router, 'fetch_inspection_validity', lambda vin: InspectionValidity('verified', expiry))
    for _ in range(2):
        challenge = vehicles_router.init_vehicle_tachometer(vehicle.id, owner, db_session)
        response = vehicles_router.submit_vehicle_tachometer(vehicle.id,
            vehicles_router.VehicleTachometerSubmitRequest(session_id=challenge.session_id, captcha_code='fixture'), owner, db_session)
        assert response.stk_valid_until == response.vehicle.stk_valid_until == expiry
        assert response.stk_validity_source == 'dataovozidlech.cz'
        db_session.expire_all()
        assert db_session.get(VehicleModel, vehicle.id).stk_valid_until == expiry
    assert db_session.query(ServiceRecord).count() == 1
    assert db_session.query(VehicleTachometerHistoryEntry).count() == 2
    evidence = json.loads(db_session.query(VehicleTachometerHistoryEntry).first().raw_payload_json)
    assert evidence['vehicle_stk_validity_at_import']['valid_until'] == expiry.isoformat()


@pytest.mark.parametrize('status', ['not_configured', 'unavailable', 'invalid_response', 'not_available'])
def test_registry_failure_preserves_stk_and_successful_mileage_import(db_session, monkeypatch, status):
    from src.modules.vehicle_hub.decoder.inspection_validity import InspectionValidity
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, 'Session', _FakeSession)
    monkeypatch.setattr(vehicles_router, 'fetch_inspection_validity', lambda vin: InspectionValidity(status))
    challenge = vehicles_router.init_vehicle_tachometer(vehicle.id, owner, db_session)
    response = vehicles_router.submit_vehicle_tachometer(vehicle.id,
        vehicles_router.VehicleTachometerSubmitRequest(session_id=challenge.session_id, captcha_code='fixture'), owner, db_session)
    assert response.vehicle.stk_valid_until == date(2030, 1, 1)
    assert response.latest_mileage_km == 416_588
    assert response.stk_valid_until is None
    assert response.stk_validity_status == status


def test_new_vehicle_lookup_returns_registry_date_before_saving(monkeypatch):
    from src.modules.vehicle_hub.decoder.inspection_validity import InspectionValidity
    monkeypatch.setattr(vehicles_router.requests, 'Session', _FakeSession)
    monkeypatch.setattr(vehicles_router, 'fetch_inspection_validity', lambda vin: InspectionValidity('verified', date(2028, 2, 29)))
    challenge = vehicles_router._create_tachometer_session(expected_vin='TMBJF73T2B9044629', vehicle_id=None, customer_id=1)
    response = vehicles_router._lookup_tachometer_with_session(session_id=challenge.session_id,
        vin='TMBJF73T2B9044629', captcha_code='fixture', customer_id=1, vehicle_id=None)
    assert response.stk_valid_until == date(2028, 2, 29)
    assert response.latest_check_date.date() == date(2025, 5, 15)  # newer identification check is NOT expiry
