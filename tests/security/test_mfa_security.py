"""MFA regressions with synthetic users and an isolated database, no mail/network."""
import hashlib
import time
from datetime import datetime, timedelta
from unittest.mock import patch
import unittest
import test_account_flows as fixture
PASSWORD = fixture.PASSWORD
from src.core import mfa
from src.modules.vehicle_hub.account_erasure import ErasedTenant
from src.core.security import decode_access_token_payload
from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings
from src.server.routers import user_security, user_auth
from src.server.security_helpers import calculate_totp


class MFASecurity(unittest.TestCase):
    register = fixture.AccountFlows.register
    tearDown = fixture.AccountFlows.tearDown
    def setUp(self):
        fixture.AccountFlows.setUp(self)
        self.client.app.include_router(user_security.router)
        for name in ['log_security_event','log_user_activity']:
            p=patch.object(user_security,name);p.start();self.patches.append(p)
        self.registered=self.register('mfa@example.com').json()
        self.uid=self.registered['user']['id']
        self.headers={'Authorization':'Bearer '+self.registered['access_token']}
        self.now=int(time.time())//30*30+2
        p=patch.object(mfa.time,'time',return_value=self.now);p.start();self.patches.append(p)

    def setup(self):
        return self.client.post('/user/security/totp/setup',headers=self.headers,json={'current_password':PASSWORD})

    def enroll(self):
        setup=self.setup();self.assertEqual(setup.status_code,200,setup.text)
        secret=setup.json()['secret'];code=calculate_totp(secret,self.now)
        response=self.client.post('/user/security/totp/enable',headers=self.headers,json={'code':code})
        self.assertEqual(response.status_code,200,response.text)
        return secret,response.json()['access_token']

    def challenge(self):
        r=self.client.post('/user/login',json={'email':'mfa@example.com','password':PASSWORD})
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['two_factor_required'])
        return r.json()['challenge_token']

    def verify(self,challenge,code):
        return self.client.post('/user/login/2fa',json={'challenge_token':challenge,'code':code})

    def test_setup_needs_password_and_never_replaces_an_active_factor(self):
        self.assertEqual(self.client.post('/user/security/totp/setup',headers=self.headers,json={}).status_code,422)
        self.assertEqual(self.client.post('/user/security/totp/setup',headers=self.headers,json={'current_password':'wrong'}).status_code,400)
        secret,token=self.enroll();self.headers={'Authorization':'Bearer '+token}
        with self.Session() as db: original=db.query(CustomerSecuritySettings).filter_by(customer_id=self.uid).one().totp_secret
        self.assertEqual(self.setup().status_code,409)
        with self.Session() as db:
            row=db.query(CustomerSecuritySettings).filter_by(customer_id=self.uid).one()
            self.assertTrue(row.two_factor_enabled);self.assertEqual(original,row.totp_secret)
            self.assertNotIn(secret,row.totp_secret)
            self.assertEqual(mfa.read_secret(row.totp_secret),secret)

    def test_pending_setup_expires_and_response_is_not_cacheable(self):
        setup=self.setup();self.assertEqual(setup.headers.get('Cache-Control'),'no-store')
        with self.Session() as db:
            db.get(mfa.MFAState,self.uid).pending_expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
        result=self.client.post('/user/security/totp/enable',headers=self.headers,json={'code':calculate_totp(setup.json()['secret'],self.now)})
        self.assertEqual(result.status_code,400)

    def test_enable_revokes_old_sessions_and_mints_verified_claims(self):
        _,token=self.enroll()
        self.assertEqual(self.client.get('/test/protected',headers=self.headers).status_code,401)
        claims=decode_access_token_payload(token)
        self.assertEqual(claims['amr'],['pwd','otp']);self.assertEqual(claims['mfa_at'],self.now)
        self.assertEqual(self.client.get('/test/protected',headers={'Authorization':'Bearer '+token}).status_code,200)

    def test_code_and_challenge_cannot_be_reused(self):
        secret,_=self.enroll();challenge=self.challenge()
        self.assertEqual(self.verify(challenge,calculate_totp(secret,self.now)).status_code,401)
        next_code=calculate_totp(secret,self.now+30)
        good=self.verify(challenge,next_code);self.assertEqual(good.status_code,200,good.text)
        self.assertEqual(self.verify(challenge,next_code).status_code,401)
        second=self.challenge();self.assertEqual(self.verify(second,next_code).status_code,401)
        with self.Session() as db:
            row=db.get(mfa.MFALoginChallenge,hashlib.sha256(second.encode()).hexdigest())
            self.assertEqual(row.attempts,1);self.assertNotIn(second,row.digest)

    def test_attempt_budget_survives_fresh_database_session(self):
        self.enroll();challenge=self.challenge()
        # Deliberately malformed digits cannot accidentally match a real OTP.
        with patch.object(user_auth,'_limit_auth'):
            for _ in range(5): self.assertEqual(self.verify(challenge,'abcdef').status_code,401)
            with self.Session() as db:
                self.assertEqual(db.get(mfa.MFALoginChallenge,hashlib.sha256(challenge.encode()).hexdigest()).attempts,5)
            self.assertEqual(self.verify(challenge,'abcdef').status_code,429)

    def test_missing_or_corrupted_active_seed_cannot_bypass_second_factor(self):
        self.enroll()
        for stored in [None,'bad','enc:v1:invalid']:
            with self.Session() as db:
                db.query(CustomerSecuritySettings).filter_by(customer_id=self.uid).one().totp_secret=stored;db.commit()
            r=self.client.post('/user/login',json={'email':'mfa@example.com','password':PASSWORD})
            self.assertEqual(r.status_code,503,r.text);self.assertNotIn('access_token',r.text)

    def test_disable_requires_unused_code_and_revokes_previous_token(self):
        secret,token=self.enroll();headers={'Authorization':'Bearer '+token}
        def disable(pw,code):
            return self.client.post('/user/security/totp/disable',headers=headers,json={'current_password':pw,'code':code})
        self.assertEqual(disable('wrong',calculate_totp(secret,self.now+30)).status_code,401)
        self.assertEqual(disable(PASSWORD,calculate_totp(secret,self.now)).status_code,400)
        r=disable(PASSWORD,calculate_totp(secret,self.now+30));self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('mfa_at',decode_access_token_payload(r.json()['access_token']))
        self.assertEqual(self.client.get('/test/protected',headers=headers).status_code,401)

    def test_expired_and_changed_account_challenges_fail_closed(self):
        self.enroll();challenge=self.challenge()
        with self.Session() as db:
            db.get(mfa.MFALoginChallenge,hashlib.sha256(challenge.encode()).hexdigest()).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
        self.assertEqual(self.verify(challenge,'123456').status_code,401)
        challenge=self.challenge()
        with self.Session() as db:
            db.get(Customer,self.uid).is_disabled=True;db.commit()
        self.assertEqual(self.verify(challenge,'123456').status_code,401)

    def make_admin(self):
        with self.Session() as db:
            db.get(Customer,self.uid).role='admin';db.commit()

    def test_admin_gate_covers_required_optional_and_browser_access(self):
        from fastapi import Depends
        from src.server.web_access import router
        from src.modules.vehicle_hub.routers_v1.auth import get_current_user_optional
        self.client.app.include_router(router)
        @self.client.app.get('/fixture/optional-admin')
        def optional(user=Depends(get_current_user_optional)):
            return {'present': user is not None}
        self.make_admin()
        self.assertFalse(self.client.get('/user/security/admin-status',headers=self.headers).json()['verified'])
        self.assertEqual(self.client.get('/user/me',headers=self.headers).status_code,200)
        denied=self.client.get('/admin-api/control-center/capabilities',headers=self.headers)
        self.assertEqual(denied.status_code,403);self.assertEqual(denied.headers['X-Admin-Verification'],'required')
        self.assertFalse(self.client.get('/fixture/optional-admin',headers=self.headers).json()['present'])
        self.assertEqual(self.client.post('/admin-web-session',headers=self.headers).status_code,403)
        _,token=self.enroll();headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.get('/admin-api/control-center/capabilities',headers=headers).status_code,200)
        self.assertEqual(self.client.post('/admin-web-session',headers=headers).status_code,200)
        with patch('src.modules.vehicle_hub.routers_v1.auth.log_user_activity'):
            self.assertTrue(self.client.get('/fixture/optional-admin',headers=headers).json()['present'])
        with patch.object(mfa.time,'time',return_value=self.now+901):
            self.assertEqual(self.client.get('/admin-api/control-center/capabilities',headers=headers).status_code,403)
            self.assertFalse(self.client.get('/user/security/admin-status',headers=headers).json()['verified'])
            self.assertEqual(self.client.post('/admin-web-session',headers=headers).status_code,403)

    def test_admin_renewal_requires_password_and_new_code_and_cannot_disable(self):
        self.make_admin();secret,token=self.enroll();headers={'Authorization':'Bearer '+token}
        def renew(password,code):
            return self.client.post('/user/security/admin-verify',headers=headers,json={'current_password':password,'code':code})
        self.assertEqual(renew('wrong',calculate_totp(secret,self.now+30)).status_code,400)
        self.assertEqual(renew(PASSWORD,calculate_totp(secret,self.now)).status_code,400)
        r=renew(PASSWORD,calculate_totp(secret,self.now+30));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.post('/user/security/totp/disable',headers=headers,json={'current_password':PASSWORD,'code':calculate_totp(secret,self.now+30)}).status_code,403)
        self.assertEqual(renew(PASSWORD,calculate_totp(secret,self.now+30)).status_code,400)

    def test_forged_assurance_claims_and_role_selection_never_grant_access(self):
        from src.core.security import create_access_token
        self.make_admin();self.enroll()
        with self.Session() as db: version=db.get(Customer,self.uid).session_version
        for extra in [{},{'amr':['pwd']},{'amr':['pwd','otp'],'mfa_at':True},{'amr':['pwd','otp'],'mfa_at':self.now+1},{'amr':['pwd','otp'],'mfa_at':self.now-901}]:
            token=create_access_token({'sub':'mfa@example.com','sv':version,**extra})
            r=self.client.get('/admin-api/control-center/capabilities',headers={'Authorization':'Bearer '+token})
            self.assertEqual(r.status_code,403,r.text)
        r=self.client.get('/admin-api/control-center/capabilities',headers={'Authorization':'Bearer invalid'})
        self.assertEqual(r.status_code,401)

    def test_account_budget_survives_new_login_challenges_and_sessions(self):
        secret,_=self.enroll()
        from fastapi import HTTPException
        for _ in range(5):
            with self.Session() as db: mfa.limit_attempt(db,self.uid,'fixture-operation')
        with self.Session() as db:
            with self.assertRaises(HTTPException) as error:
                mfa.limit_attempt(db,self.uid,'fixture-operation')
            self.assertEqual(error.exception.status_code,429)
        with patch.object(mfa.time,'time',return_value=self.now+901):
            with self.Session() as db: mfa.limit_attempt(db,self.uid,'fixture-operation')
        # A new password challenge must not reset the account's OTP attempt budget.
        with self.Session() as db:
            for _ in range(10): mfa.limit_attempt(db,self.uid,'totp-login',limit=10)
        challenge=self.challenge()
        self.assertEqual(self.verify(challenge,calculate_totp(secret,self.now+30)).status_code,429)

    def test_legacy_enrollment_is_encrypted_without_changing_codes(self):
        secret='A'*32
        with self.Session() as db:
            settings=mfa.locked_settings(db,db.get(Customer,self.uid))
            settings.totp_secret=secret;settings.two_factor_enabled=True;db.commit()
            self.assertEqual(mfa.encrypt_legacy_seeds(db),1)
            db.refresh(settings)
            self.assertNotEqual(settings.totp_secret,secret)
            self.assertEqual(mfa.read_secret(settings.totp_secret),secret)
            self.assertEqual(mfa.encrypt_legacy_seeds(db),0)
            self.assertTrue(mfa.consume_code(db,settings,calculate_totp(secret,self.now),now=self.now));db.commit()
        with self.Session() as db:
            settings=db.query(CustomerSecuritySettings).filter_by(customer_id=self.uid).one()
            self.assertFalse(mfa.consume_code(db,settings,calculate_totp(secret,self.now),now=self.now))

    def test_profile_security_and_export_never_disclose_authentication_secrets(self):
        import io,zipfile
        secret,token=self.enroll();self.headers={'Authorization':'Bearer '+token}
        with self.Session() as db: password_hash=db.get(Customer,self.uid).password_hash
        for path in ['/user/me','/user/security/settings','/user/security/admin-status']:
            r=self.client.get(path,headers=self.headers)
            self.assertEqual(r.status_code,200,r.text)
            for value in [secret,password_hash,PASSWORD,'totp_secret','password_hash']:
                self.assertNotIn(value,r.text)
        r=self.client.get('/user/me/export',headers=self.headers)
        self.assertEqual(r.status_code,200)
        with zipfile.ZipFile(io.BytesIO(r.content)) as bundle:
            for name in bundle.namelist():
                content=bundle.read(name)
                for value in [secret,password_hash,PASSWORD]: self.assertNotIn(value.encode(),content)

    def test_account_erasure_removes_mfa_state_challenges_and_budgets(self):
        _,token=self.enroll();self.challenge()
        r=self.client.request('DELETE','/user/me',headers={'Authorization':'Bearer '+token},json={
            'current_password':PASSWORD,'confirmation_text':'SMAZAT UCET','export_downloaded':False})
        self.assertEqual(r.status_code,200,r.text)
        with self.Session() as db:
            for model in [mfa.MFAState,mfa.MFALoginChallenge,mfa.MFAAttemptBudget,CustomerSecuritySettings]:
                self.assertEqual(db.query(model).filter_by(customer_id=self.uid).count(),0)
