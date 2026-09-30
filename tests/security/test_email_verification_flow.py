"""Mail verification integration in memory. All email transport is mocked."""
import hashlib
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends
from test_account_flows import AccountFlows, PASSWORD
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.routers_v1.auth import get_current_user, get_current_user_optional
from src.server.web_access import router as web_router
from src.server.routers import user_auth


class EmailVerificationFlows(AccountFlows):
    def setUp(self):
        super().setUp()
        with self.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        self.client.app.include_router(web_router)
        @self.client.app.get('/fixture/v1')
        def v1(user=Depends(get_current_user)):
            return {'id': user.id}
        @self.client.app.get('/fixture/optional')
        def optional(user=Depends(get_current_user_optional)):
            return {'authenticated': user is not None}

    def pending_account(self):
        self.mocks[-1].reset_mock()
        response = self.client.post('/user/register', json={'email':'pending@example.com','password':PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        calls = self.mocks[-1].call_args_list
        self.assertEqual(len(calls), 1, 'Send one verification email, not a contradictory welcome email')
        call = calls[0]
        body = call.kwargs.get('body') if call.kwargs else call.args[2]
        url = body.split('adresu: ', 1)[1].split('\n', 1)[0]
        self.assertEqual(urlsplit(url).query, '')
        token = parse_qs(urlsplit(url).fragment)['token'][0]
        headers = {'Authorization':'Bearer '+response.json()['access_token']}
        return response.json()['user']['id'], token, headers

    def test_real_link_unblocks_required_and_optional_auth_once(self):
        customer_id, token, headers = self.pending_account()
        with self.Session() as db:
            row = db.get(EmailVerification, customer_id)
            self.assertNotIn(token, row.token_digest)
        self.assertEqual(self.client.get('/fixture/v1', headers=headers).status_code, 403)
        self.assertFalse(self.client.get('/fixture/optional', headers=headers).json()['authenticated'])
        with patch('src.modules.vehicle_hub.routers_v1.auth.log_user_activity'):
            result = self.client.post('/user/email-verification/confirm', json={'token': token})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(self.client.get('/fixture/v1', headers=headers).status_code, 200)
            self.assertTrue(self.client.get('/fixture/optional', headers=headers).json()['authenticated'])
        self.assertEqual(self.client.post('/user/email-verification/confirm', json={'token': token}).status_code, 400)
        self.assertEqual(self.client.get('/user/email-verification', headers=headers).json(), {'required':False,'verified':True})

    def test_expired_link_cannot_verify(self):
        customer_id, token, _ = self.pending_account()
        with self.Session() as db:
            db.get(EmailVerification, customer_id).expires_at = datetime.utcnow()-timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.post('/user/email-verification/confirm',json={'token':token}).status_code, 400)

    def test_resend_replaces_old_link_and_respects_cooldown(self):
        customer_id, old_token, headers = self.pending_account()
        early = self.client.post('/user/email-verification/resend', headers=headers)
        self.assertEqual(early.status_code, 429)
        self.assertEqual(early.headers['Retry-After'], '60')
        with self.Session() as db:
            db.get(EmailVerification, customer_id).sent_at = datetime.utcnow()-timedelta(minutes=2)
            db.commit()
        self.assertEqual(self.client.post('/user/email-verification/resend', headers=headers).status_code, 200)
        call=self.mocks[-1].call_args
        url=call.args[2].split('adresu: ',1)[1].split('\n',1)[0]
        new_token=parse_qs(urlsplit(url).fragment)['token'][0]
        self.assertNotEqual(old_token,new_token)
        self.assertEqual(self.client.post('/user/email-verification/confirm',json={'token':old_token}).status_code,400)
        self.assertEqual(self.client.post('/user/email-verification/confirm',json={'token':new_token}).status_code,200)

    def test_failed_delivery_keeps_gate_and_revokes_undelivered_token(self):
        self.mocks[-1].side_effect=RuntimeError('provider-private-diagnostic')
        response=self.client.post('/user/register',json={'email':'pending@example.com','password':PASSWORD})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['email_sent'])
        self.assertNotIn('provider-private', response.text)
        with self.Session() as db:
            row=db.get(EmailVerification,response.json()['user']['id'])
            self.assertIsNone(row.verified_at)
            self.assertIsNone(row.token_digest)
            self.assertIsNone(row.expires_at)
        headers={'Authorization':'Bearer '+response.json()['access_token']}
        self.assertEqual(self.client.get('/test/protected',headers=headers).status_code,403)
        self.assertTrue(self.client.get('/user/email-verification',headers=headers).json()['required'])

    def test_legacy_resend_does_not_create_new_restriction(self):
        customer_id, _, headers=self.pending_account()
        with self.Session() as db:
            db.query(EmailVerification).filter_by(customer_id=customer_id).delete(); db.commit()
        self.mocks[-1].reset_mock()
        self.assertEqual(self.client.post('/user/email-verification/resend',headers=headers).status_code,200)
        self.mocks[-1].assert_not_called()
        self.assertEqual(self.client.get('/test/protected',headers=headers).status_code,200)
        with self.Session() as db: self.assertIsNone(db.get(EmailVerification,customer_id))

    def test_unverified_account_can_delete_itself_without_email_access(self):
        customer_id, _, headers=self.pending_account()
        response=self.client.request('DELETE','/user/me',headers=headers,json={
            'current_password':PASSWORD,'confirmation_text':'SMAZAT UCET','export_downloaded':True})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['deleted'])
        with self.Session() as db:
            self.assertIsNone(db.get(Customer,customer_id))
            self.assertIsNone(db.get(EmailVerification,customer_id))

    def test_unverified_admin_cannot_bypass_gate_via_browser_cookie(self):
        customer_id, _, headers=self.pending_account()
        with self.Session() as db:
            db.get(Customer,customer_id).role='admin'; db.commit()
        self.assertEqual(self.client.post('/admin-web-session',headers=headers).status_code,403)

    def test_disabled_account_cannot_confirm_old_link(self):
        customer_id, token, _=self.pending_account()
        with self.Session() as db:
            db.get(Customer,customer_id).is_disabled=True; db.commit()
        self.assertEqual(self.client.post('/user/email-verification/confirm',json={'token':token}).status_code,400)

    def test_service_requires_admin_approval(self):
        super().test_service_requires_admin_approval()
        login=self.client.post('/user/login',json={'email':'service@example.com','password':PASSWORD}).json()
        headers={'Authorization':'Bearer '+login['access_token']}
        self.assertTrue(self.client.get('/user/email-verification',headers=headers).json()['required'])
        self.assertEqual(self.client.get('/fixture/v1',headers=headers).status_code,403)
        call=self.mocks[-1].call_args
        token=parse_qs(urlsplit(call.args[2].split('adresu: ',1)[1].split('\n',1)[0]).fragment)['token'][0]
        self.assertEqual(self.client.post('/user/email-verification/confirm',json={'token':token}).status_code,200)
        with patch('src.modules.vehicle_hub.routers_v1.auth.log_user_activity'):
            self.assertEqual(self.client.get('/fixture/v1',headers=headers).status_code,200)

    def test_failure_of_pending_record_creation_does_not_commit_account(self):
        with patch.object(user_auth,'prepare_verification',side_effect=RuntimeError('fixture DB failure')):
            with self.assertRaises(RuntimeError):
                self.client.post('/user/register',json={'email':'not-created@example.com','password':PASSWORD})
        with self.Session() as db:
            self.assertIsNone(db.query(Customer).filter_by(email='not-created@example.com').first())
