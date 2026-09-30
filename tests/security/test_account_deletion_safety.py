"""Reauthentication safeguards, using a disposable database and no real erasure."""
import os
import tempfile
import unittest
from unittest.mock import patch

sandbox = tempfile.TemporaryDirectory(prefix="account-erasure-safety-")
os.environ.update(
    DATABASE_URL="sqlite:///" + sandbox.name + "/unused.sqlite",
    DATA_DIR_PATH=sandbox.name,
    JWT_SECRET_KEY="isolated-account-erasure-fixture-not-for-deployment",
    ENVIRONMENT="test",
)
os.environ.pop("DATABASE_SCHEMA", None)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.auth import get_current_user_email
from src.core.rate_limiter import rate_limiter
from src.core.security import hash_password
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.server.routers import user_account


class AccountDeletionSafety(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", lambda db, _: db.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            tenant = Tenant(name="Erasure fixture", license_key="erasure-fixture")
            db.add(tenant)
            db.flush()
            db.add(Customer(tenant_id=tenant.id, email="owner@example.test", name="Original",
                            password_hash=hash_password("Fixture-password-654!")))
            db.commit()
        app = FastAPI()
        app.include_router(user_account.router)

        def get_test_db():
            with self.Session() as db:
                yield db

        app.dependency_overrides[get_db] = get_test_db
        app.dependency_overrides[get_current_user_email] = lambda: "owner@example.test"
        self.client = TestClient(app)
        self.erase = patch.object(user_account, "delete_customer_account", return_value={"customers": 1})
        self.mock_erase = self.erase.start()
        rate_limiter.clear()

    def tearDown(self):
        self.erase.stop()
        self.client.close()
        self.engine.dispose()
        rate_limiter.clear()

    def request(self, **changes):
        body = {"current_password": "Fixture-password-654!", "confirmation_text": "SMAZAT UCET",
                "export_downloaded": True}
        body.update(changes)
        return self.client.request("DELETE", "/user/me", json=body)

    def test_wrong_password_never_reaches_erasure(self):
        response = self.request(current_password="wrong-fixture")
        self.assertEqual(response.status_code, 400)
        self.mock_erase.assert_not_called()

    def test_confirmation_failure_never_reaches_erasure(self):
        self.assertEqual(self.request(confirmation_text="maybe").status_code, 400)
        self.mock_erase.assert_not_called()

    def test_export_is_optional(self):
        self.assertEqual(self.request(export_downloaded=False).status_code, 200)
        self.mock_erase.assert_called_once()

    def test_sixth_password_attempt_is_throttled(self):
        with patch.object(user_account, "verify_password", return_value=False) as verifier:
            for _ in range(5):
                self.assertEqual(self.request(current_password="wrong-fixture").status_code, 400)
            response = self.request()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "900")
        self.assertEqual(verifier.call_count, 5)
        self.mock_erase.assert_not_called()

    def test_failure_rolls_back_and_does_not_expose_database_details(self):
        def fail_after_change(customer, *, db, **_):
            customer.name = "Uncommitted change"
            db.flush()
            raise RuntimeError("private-database-value: password_hash=do-not-expose")
        self.mock_erase.side_effect = fail_after_change
        response = self.request()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-database-value", response.text)
        self.assertNotIn("password_hash", response.text)
        with self.Session() as db:
            self.assertEqual(db.query(Customer).one().name, "Original")

    def test_only_confirmed_success_reports_deleted(self):
        response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.mock_erase.assert_called_once()

    def test_missing_password_hash_never_deletes_account(self):
        with self.Session() as db:
            db.query(Customer).one().password_hash = None
            db.commit()
        self.assertEqual(self.request().status_code, 400)
        self.mock_erase.assert_not_called()
