"""Persistent session renewal, revocation and account isolation using isolated HTTP fixtures."""
from datetime import datetime, timedelta
from unittest.mock import patch
from test_account_flows import AccountFlows
from src.server.routers.user_security import router
from src.core.security import create_access_token, decode_access_token_payload
from src.core.session_revocation import RevokedAccessToken
from src.modules.vehicle_hub.models import Customer


class SessionRenewal(AccountFlows):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(router)

    def test_renewed_session_survives_original_expiry_and_old_logout_revokes_it(self):
        old = self.register().json()['access_token']
        headers = {'Authorization': 'Bearer ' + old}
        result = self.client.post('/user/session/renew', headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        new = result.json()['access_token']
        before, after = decode_access_token_payload(old), decode_access_token_payload(new)
        self.assertEqual(before['jti'], after['jti'])
        self.assertEqual(before['sub'], after['sub'])
        self.assertGreater(after['exp'], before['exp'])
        self.assertNotIn('mfa_at', after)
        self.assertEqual(self.client.get('/user/me', headers={'Authorization': 'Bearer '+new}).status_code, 200)
        self.assertEqual(self.client.post('/user/logout', json={'logout_ticket': before['logout_ticket']}).status_code, 204)
        for token in (old, new):
            h = {'Authorization': 'Bearer '+token}
            self.assertEqual(self.client.post('/user/session/renew', headers=h).status_code, 401)
            self.assertEqual(self.client.get('/user/me', headers=h).status_code, 401)
        with self.Session() as db:
            self.assertGreaterEqual(db.query(RevokedAccessToken).one().expires_at.timestamp(), after['exp'])

    def test_disabled_or_revoked_account_cannot_renew(self):
        result = self.register().json(); token = result['access_token']; uid = result['user']['id']
        headers = {'Authorization': 'Bearer '+token}
        with self.Session() as db:
            user = db.get(Customer, uid); user.is_disabled = True; db.commit()
        self.assertEqual(self.client.post('/user/session/renew', headers=headers).status_code, 401)
        with self.Session() as db:
            user = db.get(Customer, uid); user.is_disabled = False; user.session_version += 1; db.commit()
        self.assertEqual(self.client.post('/user/session/renew', headers=headers).status_code, 401)

    def test_expired_and_invalid_credentials_never_refresh(self):
        result = self.register().json(); claims = decode_access_token_payload(result['access_token'])
        expired = create_access_token({'sub': claims['sub'], 'sv': claims['sv']}, expires_delta=timedelta(seconds=-1))
        for token in (expired, 'invalid'):
            self.assertEqual(self.client.post('/user/session/renew', headers={'Authorization':'Bearer '+token}).status_code, 401)
