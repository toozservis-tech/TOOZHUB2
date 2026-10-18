"""Regression tests for status reads and tenant FK-compatible mutation locks."""
from src.modules.vehicle_hub.models import Tenant, LicenseSubscription
from src.modules.vehicle_hub.routers_v1.license_status import _get_subscription


class QuerySpy:
    def __init__(self, model, events):
        self.model = model
        self.events = events

    def filter(self, *_args):
        return self

    def filter_by(self, **_kwargs):
        return self

    def with_for_update(self, **kwargs):
        self.events.append(("lock", self.model, kwargs))
        return self

    def populate_existing(self):
        return self

    def one(self):
        return object()

    def first(self):
        return self.model


class SessionSpy:
    def __init__(self):
        self.events = []

    def query(self, model):
        self.events.append(("query", model))
        return QuerySpy(model, self.events)


def test_license_status_read_does_not_lock_tenant_or_subscription():
    db = SessionSpy()
    assert _get_subscription(db, 101, for_update=False) is LicenseSubscription
    assert db.events == [("query", LicenseSubscription)]


def test_subscription_write_serializes_without_blocking_tenant_fk_reads():
    db = SessionSpy()
    assert _get_subscription(db, 101) is LicenseSubscription
    assert ("lock", Tenant, {"key_share": True}) in db.events
    assert ("lock", LicenseSubscription, {}) in db.events
