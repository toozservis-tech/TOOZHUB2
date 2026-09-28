"""Isolated account security regressions: no live database or email delivery."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

sandbox = tempfile.TemporaryDirectory()
os.environ.update(DATABASE_URL='sqlite:///' + sandbox.name + '/test.sqlite', DATA_DIR_PATH=sandbox.name,
                  JWT_SECRET_KEY='test-only-secret-key-not-for-deployment-123456', ENVIRONMENT='test')
os.environ.pop('DATABASE_SCHEMA', None)
os.environ.pop('RESEND_API_KEY', None)
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.server.routers import user_auth, user_account, system
from src.server import admin_api
from src.core.auth import get_current_user_email
from src.core.rate_limiter import rate_limiter
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer
from src.modules.email_client.service import EmailService

PASSWORD = 'Long-test-password-428!'

class AccountFlows(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        def db():
            with self.Session() as session:
                yield session
        app = FastAPI()
        app.include_router(user_auth.router)
        app.include_router(user_account.router)
        app.include_router(system.router)
        app.include_router(admin_api.router)
        app.dependency_overrides[get_db] = db
        @app.get('/test/protected')
        def protected(email=Depends(get_current_user_email)):
            return {'email': email}
        self.client = TestClient(app)
        self.patches = [
            patch.object(user_auth, 'send_registration_alert_email', return_value={'status':'no_recipients'}),
            patch.object(user_account, 'log_user_activity'),
            patch.object(user_auth, 'log_security_event'),
            patch.object(user_auth, 'get_active_ip_block', return_value=None),
            patch('src.core.auth.ensure_customer_account_state_schema'),
            patch.object(admin_api, 'ensure_customer_account_state_schema'),
            patch.object(admin_api, 'log_developer_action'),
            patch.object(EmailService, 'is_configured', return_value=True),
            patch.object(EmailService, 'send_simple_email', return_value=True),
        ]
        self.mocks = [p.start() for p in self.patches]
        rate_limiter.clear()
    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.engine.dispose()
    def register(self, email='user@example.com', **extra):
        return self.client.post('/user/register', json={'email':email,'password':PASSWORD,'name':'Security Test',**extra})
    def test_registration_login_and_role_cannot_be_injected(self):
        r=self.register(role='admin',tenant_id=1);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['user']['role'],'user')
        other=self.register('other@example.com');self.assertEqual(other.status_code,200,other.text)
        with self.Session() as db:
            self.assertEqual(len({u.tenant_id for u in db.query(Customer).all()}),2)
        self.assertEqual(self.register('USER@example.com').status_code,400)
        login=self.client.post('/user/login',json={'email':'USER@example.com','password':PASSWORD})
        self.assertEqual(login.status_code,200,login.text)
        headers={'Authorization':'Bearer '+login.json()['access_token']}
        self.assertEqual(self.client.get('/admin-api/service-registration-requests',headers=headers).status_code,403)
    def test_password_recovery_one_use_expiry_and_session_revocation(self):
        registered=self.register();old=registered.json()['access_token']
        recovery=self.client.post('/user/forgot-password',json={'email':'user@example.com'})
        unknown=self.client.post('/user/forgot-password',json={'email':'absent@example.com'})
        self.assertEqual(recovery.json(),unknown.json())
        message=self.mocks[-1].call_args.kwargs['body']
        url=message.split('otevřete ',1)[1].split('\n')[0]
        token=parse_qs(urlsplit(url).fragment)['token'][0]
        with self.Session() as db:
            user=db.query(Customer).one()
            self.assertNotIn(token,user.reset_token)
            self.assertTrue(user.reset_token.startswith('sha256:'))
        response=self.client.post('/user/reset-password',json={'token':token,'new_password':'New-strong-password-985!'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post('/user/reset-password',json={'token':token,'new_password':PASSWORD}).status_code,400)
        self.assertEqual(self.client.get('/test/protected',headers={'Authorization':'Bearer '+old}).status_code,401)
        self.assertEqual(self.client.post('/user/login',json={'email':'user@example.com','password':PASSWORD}).status_code,401)
        self.assertEqual(self.client.post('/user/login',json={'email':'user@example.com','password':'New-strong-password-985!'}).status_code,200)
        self.client.post('/user/forgot-password',json={'email':'user@example.com'})
        token=parse_qs(urlsplit(self.mocks[-1].call_args.kwargs['body'].split('otevřete ',1)[1].split('\n')[0]).fragment)['token'][0]
        with self.Session() as db:
            db.query(Customer).one().reset_token_expires=datetime.utcnow()-timedelta(seconds=1);db.commit()
        self.assertEqual(self.client.post('/user/reset-password',json={'token':token,'new_password':PASSWORD}).status_code,400)
    def test_password_rules_outages_and_throttle(self):
        for pw in ['123456','aaaaaaaaaaaa','é'*40]:
            self.assertEqual(self.register(password=pw).status_code,400)
        with patch.object(EmailService,'is_configured',return_value=False):
            for email in ['user@example.com','absent@example.com']:
                self.assertEqual(self.client.post('/user/forgot-password',json={'email':email}).status_code,503)
        rate_limiter.clear()
        for _ in range(3):
            self.assertEqual(self.client.post('/user/forgot-password',json={'email':'absent@example.com'}).status_code,200)
        self.assertEqual(self.client.post('/user/request-password-reset',json={'email':'absent@example.com'}).status_code,429)
    def test_production_diagnostics_never_expose_database(self):
        r=self.register();headers={'Authorization':'Bearer '+r.json()['access_token']}
        with patch.object(system,'ENVIRONMENT','production'):
            for path in ['/health/config','/api/_debug/routes','/api/_debug/db_stats']:
                self.assertEqual(self.client.get(path,headers=headers).status_code,404)

    def test_password_change_invalidates_pending_two_factor_challenge(self):
        self.register()
        challenge={'email':'user@example.com','session_version':0,'expires_at':__import__('time').time()+60,'attempts':0}
        with self.Session() as db:
            db.query(Customer).one().session_version=1;db.commit()
        with patch.object(user_auth,'get_2fa_login_challenge',return_value=challenge):
            response=self.client.post('/user/login/2fa',json={'challenge_token':'x'*43,'code':'123456'})
        self.assertEqual(response.status_code,401,response.text)

    def test_change_password_revokes_old_session(self):
        r=self.register();headers={'Authorization':'Bearer '+r.json()['access_token']}
        changed=self.client.put('/user/change-password',headers=headers,json={'current_password':PASSWORD,'new_password':'Changed-password-789!'})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(self.client.get('/test/protected',headers=headers).status_code,401)

    def test_email_failure_does_not_leak_account_or_leave_reset_token(self):
        self.register()
        with patch.object(EmailService,'send_simple_email',side_effect=RuntimeError('secret-provider-diagnostic')):
            result=self.client.post('/user/forgot-password',json={'email':'user@example.com'})
        self.assertEqual(result.status_code,200)
        self.assertNotIn('secret-provider',result.text)
        with self.Session() as db:
            self.assertIsNone(db.query(Customer).one().reset_token)

    def test_service_requires_admin_approval(self):
        r=self.register('admin@example.com');self.assertEqual(r.status_code,200,r.text)
        with self.Session() as db:
            db.query(Customer).one().role='admin';db.commit()
        headers={'Authorization':'Bearer '+r.json()['access_token']}
        payload={'email':'service@example.com','password':PASSWORD,'ico':'12345678','service_name':'Test Service',
                 'responsible_person':'Test Person','phone':'+420123456789','street':'Test Street','city':'Test City',
                 'zip':'12345','registration_purpose':'Isolated automated security test'}
        r=self.client.post('/user/register/service-request',json=payload);self.assertEqual(r.status_code,200,r.text)
        rid=r.json()['request_id'];self.assertEqual(r.json()['status'],'pending')
        self.assertEqual(self.client.post('/user/login',json={'email':payload['email'],'password':PASSWORD}).status_code,401)
        r=self.client.post(f'/admin-api/service-registration-requests/{rid}/approve',headers=headers,json={'review_note':'Automated isolated test'})
        self.assertEqual(r.status_code,200,r.text)
        login=self.client.post('/user/login',json={'email':payload['email'],'password':PASSWORD,'expected_role':'service'})
        self.assertEqual(login.status_code,200,login.text);self.assertEqual(login.json()['user']['role'],'service')
        self.assertEqual(self.client.post(f'/admin-api/service-registration-requests/{rid}/approve',headers=headers,json={}).status_code,400)

if __name__ == '__main__': unittest.main()
