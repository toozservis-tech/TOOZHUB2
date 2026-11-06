"""Recipient-scoped readiness: a global canary is not delivery for every account."""
import json
import os
import unittest
from unittest.mock import patch
import pytest
import test_notification_delivery as fixture
from src.modules.vehicle_hub.push_delivery import public_status

@pytest.mark.parametrize('enabled,raw,expected77,expected78,valid,limited',[
    ('true','77',True,False,True,True),
    ('true','77,78',True,True,True,True),
    ('true','78',False,True,True,True),
    ('true','77,',False,False,False,True),
    ('true','not-an-id',False,False,False,True),
    ('false','77',False,False,True,True),
    ('false','',False,False,True,True),
    ('true','',False,False,True,True),
    ('true','  ',False,False,True,True),
])
def test_effective_status_for_77_and_78_hides_allowlist(monkeypatch,enabled,raw,expected77,expected78,valid,limited):
    monkeypatch.delenv('PUSH_PUBLIC_APNS_FROM_UTC',raising=False)
    monkeypatch.setenv('PUSH_DELIVERY_ENABLED',enabled)
    monkeypatch.setenv('PUSH_DELIVERY_RECIPIENT_IDS',raw)
    for recipient,expected in [(77,expected77),(78,expected78)]:
        status=public_status(recipient)
        assert status['dispatch_enabled'] is expected
        assert status['dispatch_configuration_valid'] is valid
        assert status['dispatch_limited'] is limited
        assert not any(key in status for key in ('recipient_id','recipients','allowed_ids','recipient_ids'))
        assert '77' not in json.dumps(status) and '78' not in json.dumps(status)
    assert public_status()['dispatch_enabled'] is (enabled=='true' and valid and bool(raw.strip()))

def test_absent_policy_and_environment_changes_recompute_without_cached_account(monkeypatch):
    monkeypatch.setenv('PUSH_DELIVERY_ENABLED','true');monkeypatch.delenv('PUSH_DELIVERY_RECIPIENT_IDS',raising=False)
    monkeypatch.delenv('PUSH_PUBLIC_APNS_FROM_UTC',raising=False)
    assert not public_status(77)['dispatch_enabled'] and not public_status(78)['dispatch_enabled']
    monkeypatch.setenv('PUSH_DELIVERY_RECIPIENT_IDS','77')
    assert public_status(77)['dispatch_enabled'] and not public_status(78)['dispatch_enabled']
    monkeypatch.setenv('PUSH_DELIVERY_RECIPIENT_IDS','78')
    assert not public_status(77)['dispatch_enabled'] and public_status(78)['dispatch_enabled']

class RecipientStatusHTTP(unittest.TestCase):
    setUp=fixture.Delivery.setUp
    tearDown=fixture.Delivery.tearDown
    register=fixture.Delivery.register
    verified_admin_token=fixture.Delivery.verified_admin_token

    def test_authenticated_route_uses_identity_not_requested_account_and_is_no_store(self):
        route='/api/v1/push/device-status'
        allowed=self.user['user']['id'];excluded=self.other['user']['id']
        with patch.dict(os.environ,{'PUSH_DELIVERY_RECIPIENT_IDS':str(allowed)}):
            yes=self.client.get(route,headers=self.uh)
            no=self.client.get(route+'?recipient_id='+str(allowed),headers=self.oh)
            self.assertEqual(yes.status_code,200);self.assertEqual(no.status_code,200)
            self.assertTrue(yes.json()['dispatch_enabled']);self.assertFalse(no.json()['dispatch_enabled'])
            self.assertEqual(no.headers['cache-control'],'no-store')
            self.assertEqual(yes.json()['providers'],no.json()['providers'])
            self.assertEqual(yes.json()['registration_available'],no.json()['registration_available'])
            self.assertNotIn('recipient_id',no.json())
            self.assertEqual(self.client.get(route).status_code,401)
        with patch.dict(os.environ,{'PUSH_DELIVERY_RECIPIENT_IDS':str(excluded)}):
            self.assertFalse(self.client.get(route,headers=self.uh).json()['dispatch_enabled'])
            self.assertTrue(self.client.get(route,headers=self.oh).json()['dispatch_enabled'])
