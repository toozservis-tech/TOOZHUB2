"""Security events retain their purpose without silently sharing location."""
import importlib
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sandbox = tempfile.TemporaryDirectory(prefix="location-privacy-")
os.environ.update(DATABASE_URL="sqlite:///" + sandbox.name + "/unused.sqlite",
                  DATA_DIR_PATH=sandbox.name, ENVIRONMENT="test")
os.environ.pop("DATABASE_SCHEMA", None)

from starlette.requests import Request
from src.server import security_tracking as tracking


class LocationPrivacy(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ)
        self.env.start()
        for name in ("ENABLE_IP_GEOLOOKUP", "ENABLE_BROWSER_GEOLOCATION_OVERRIDE", "ENABLE_REVERSE_GEOCODE"):
            os.environ.pop(name, None)
        importlib.reload(tracking)
        self.network = patch.object(tracking, "urlopen", side_effect=AssertionError("Unexpected external request"))
        self.open = self.network.start()

    def tearDown(self):
        self.network.stop()
        self.env.stop()
        importlib.reload(tracking)

    def request(self, latitude="50.075501"):
        return Request({"type": "http", "method": "GET", "path": "/user/me",
                        "client": ("8.8.8.8", 443), "query_string": b"",
                        "headers": [(b"user-agent", b"privacy-fixture"),
                                    (b"x-geo-lat", latitude.encode()), (b"x-geo-lon", b"14.437801")]})

    def test_external_enrichment_is_opt_in(self):
        self.assertFalse(tracking._GEOLOOKUP_ENABLED)
        self.assertFalse(tracking._BROWSER_GEO_ENABLED)
        self.assertFalse(tracking._REVERSE_GEO_ENABLED)
        self.assertIsNone(tracking.lookup_ip_location("8.8.8.8"))
        self.assertIsNone(tracking.reverse_geocode_location(50.075501, 14.437801))
        self.assertIsNone(tracking._extract_browser_geo(self.request()))
        self.open.assert_not_called()

    def test_login_audit_keeps_security_fields_without_coordinates(self):
        session = MagicMock()
        with patch.object(tracking, "SessionLocal", return_value=session):
            tracking.log_security_event(event_type="login_success", request=self.request(),
                                        customer_id=7, user_email="fixture@example.test", tenant_id=4)
        entry = session.add.call_args.args[0]
        self.assertEqual(entry.customer_id, 7)
        self.assertEqual(entry.ip_address, "8.8.8.8")
        self.assertEqual(entry.user_agent, "privacy-fixture")
        self.assertIsNone(entry.latitude)
        self.assertIsNone(entry.longitude)
        self.assertIsNone(entry.city)
        session.commit.assert_called_once()
        self.open.assert_not_called()

    def test_even_explicit_opt_in_rejects_invalid_coordinates(self):
        with patch.object(tracking, "_BROWSER_GEO_ENABLED", True):
            for value in ("nan", "inf", "-inf", "91", "-91", "not-a-number"):
                self.assertIsNone(tracking._extract_browser_geo(self.request(value)))

    def test_explicit_operator_setting_can_enable_enrichment(self):
        os.environ.update(ENABLE_IP_GEOLOOKUP="1", ENABLE_BROWSER_GEOLOCATION_OVERRIDE="true",
                          ENABLE_REVERSE_GEOCODE="yes")
        importlib.reload(tracking)
        self.assertTrue(tracking._GEOLOOKUP_ENABLED)
        self.assertTrue(tracking._BROWSER_GEO_ENABLED)
        self.assertTrue(tracking._REVERSE_GEO_ENABLED)
        self.assertEqual(tracking._extract_browser_geo(self.request())["latitude"], 50.075501)
