"""Pre-purchase account checks never transfer a subscription or grant access."""
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

from src.modules.vehicle_hub.routers_v1 import apple_billing as api
from test_apple_billing import setup, signed_state, sync
from src.modules.licensing import apple_store as store
from src.modules.licensing.apple_models import AppleSubscription
from src.modules.vehicle_hub.models import Customer, Tenant, License


def check(db, user):
    return api.check_purchase_account(api.SignedTransaction(signed_transaction="fixture-signed-history"), user, db)


def second_user(db):
    db.add(Tenant(id=32, name="Other fixture", license_key="other-fixture"))
    db.flush()
    user = Customer(id=32, tenant_id=32, email="other@example.invalid", name="Other", role="user")
    db.add(user); db.flush()
    db.add(License(tenant_id=32, plan="free", status="active", vehicles_limit=1))
    identity = store.identity_for_user(db, user)
    db.commit()
    return user, identity


def test_own_history_is_allowed_without_granting_or_claiming_it(setup, monkeypatch):
    db, user, *_ = setup
    signed_state(setup, monkeypatch)
    assert check(db, user) == {"can_purchase": True, "message": None}
    assert db.query(License).one().plan == "free"
    assert db.query(AppleSubscription).count() == 0


def test_changed_apple_token_cannot_move_original_subscription(setup, monkeypatch):
    db, owner, identity, _ = setup
    tx, *_ = signed_state(setup, monkeypatch)
    sync(setup)
    other, other_identity = second_user(db)
    tx.appAccountToken = other_identity.token  # Apple token changed on an upgrade.
    assert check(db, owner)["can_purchase"] is True
    blocked = check(db, other)
    assert blocked["can_purchase"] is False
    assert "jiného účtu" in blocked["message"]
    assert "example.invalid" not in blocked["message"]
    assert db.query(AppleSubscription).one().account_token == identity.token
    assert db.query(License).filter_by(tenant_id=32).one().plan == "free"


def test_unclaimed_foreign_history_still_blocks_a_purchase(setup, monkeypatch):
    db, owner, *_ = setup
    tx, *_ = signed_state(setup, monkeypatch)
    other, other_identity = second_user(db)
    tx.appAccountToken = other_identity.token
    assert check(db, owner)["can_purchase"] is False
    assert check(db, other)["can_purchase"] is True
    assert db.query(AppleSubscription).count() == 0


def test_deleted_original_owner_does_not_release_purchase_to_other_account(setup, monkeypatch):
    db, owner, identity, _ = setup
    tx, *_ = signed_state(setup, monkeypatch)
    sync(setup)
    other, other_identity = second_user(db)
    identity.customer_id = None
    identity.tenant_id = None
    db.commit()
    tx.appAccountToken = other_identity.token
    assert check(db, other)["can_purchase"] is False
    assert db.query(AppleSubscription).one().account_token == identity.token
    assert db.query(License).filter_by(tenant_id=32).one().plan == "free"


def test_account_identity_from_previous_tenant_is_rejected(setup, monkeypatch):
    db, owner, *_ = setup
    signed_state(setup, monkeypatch)
    other, _ = second_user(db)
    owner.tenant_id = other.tenant_id
    db.commit()
    with pytest.raises(HTTPException) as error: check(db, owner)
    assert error.value.status_code == 409
    assert db.query(AppleSubscription).count() == 0


@pytest.mark.parametrize("field,value", [("bundleId", "other-app"), ("productId", "other-product"),
    ("subscriptionGroupIdentifier", "other-group"), ("appAccountToken", None)])
def test_invalid_history_metadata_is_rejected(setup, monkeypatch, field, value):
    db, owner, *_ = setup
    tx, *_ = signed_state(setup, monkeypatch)
    setattr(tx, field, value)
    with pytest.raises(HTTPException): check(db, owner)
    assert db.query(AppleSubscription).count() == 0
    assert db.query(License).one().plan == "free"


def test_bad_signature_does_not_become_purchase_permission(setup, monkeypatch):
    db, owner, *_ = setup
    def invalid(_): raise VerificationException(VerificationStatus.VERIFICATION_FAILURE)
    monkeypatch.setattr(store, "apple_services", lambda _: (NS(verify_and_decode_signed_transaction=invalid), None))
    with pytest.raises(HTTPException) as error: check(db, owner)
    assert error.value.status_code == 400
    assert db.query(AppleSubscription).count() == 0
