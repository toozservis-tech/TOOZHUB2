"""Per-session logout, durable replay denial, and offline revocation tickets."""
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch
from fastapi import Depends
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from test_account_flows import AccountFlows, PASSWORD
from src.core.security import create_access_token, decode_access_token_payload, decode_logout_ticket
from src.core.session_revocation import RevokedAccessToken, token_digest, require_active_token, revoke_tokens
from src.server.web_access import router as web_router, AdminStaticFiles
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.routers_v1.auth import get_current_user_optional
from src.modules.vehicle_hub.models import Customer


class SessionRevocation(AccountFlows):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(web_router)
        @self.client.app.get('/fixture/optional')
        def optional(user=Depends(get_current_user_optional)):
            return {'present': user is not None}

    def login(self):
        return self.client.post('/user/login',json={'email':'user@example.com','password':PASSWORD}).json()['access_token']

    def headers(self, token):
        return {'Authorization':'Bearer '+token}

    def test_logout_revokes_only_one_session_and_is_idempotent(self):
        token=self.register().json()['access_token']; other=self.login()
        self.assertNotEqual(token, other)
        for _ in range(2):
            self.assertEqual(self.client.post('/user/logout',headers=self.headers(token)).status_code,204)
        self.assertEqual(self.client.get('/test/protected',headers=self.headers(token)).status_code,401)
        self.assertEqual(self.client.get('/fixture/optional',headers=self.headers(token)).status_code,401)
        self.assertEqual(self.client.get('/test/protected',headers=self.headers(other)).status_code,200)
        with self.Session() as db:
            row=db.query(RevokedAccessToken).one()
            self.assertEqual(row.digest,token_digest(token))
            self.assertNotIn(token, repr(row.__dict__))
            self.assertNotIn('user@example.com',repr(row.__dict__))
            self.assertEqual(db.query(Customer).one().session_version,0)

    def test_offline_ticket_cannot_authenticate_but_revokes_its_own_session(self):
        token=self.register().json()['access_token']; other=self.login()
        ticket=decode_access_token_payload(token)['logout_ticket']
        self.assertIsNone(decode_access_token_payload(ticket))
        self.assertEqual(self.client.get('/test/protected',headers=self.headers(ticket)).status_code,401)
        self.assertEqual(self.client.post('/admin-web-session',headers=self.headers(ticket)).status_code,401)
        for _ in range(2):
            self.assertEqual(self.client.post('/user/logout',json={'logout_ticket':ticket}).status_code,204)
        self.assertEqual(self.client.get('/test/protected',headers=self.headers(token)).status_code,401)
        self.assertEqual(self.client.get('/test/protected',headers=self.headers(other)).status_code,200)
        # A normal bearer isn't a revocation ticket (different purpose/signature).
        self.assertIsNone(decode_logout_ticket(other))

    def test_cookie_logout_denies_replay_and_does_not_revoke_a_newer_cookie(self):
        user=self.register().json()['user']
        with self.Session() as db:
            db.get(Customer,user['id']).role='admin';db.commit()
        old=self.verified_admin_token(user['id']);new=self.verified_admin_token(user['id'])
        r=self.client.delete('/admin-web-session',headers={**self.headers(old),'Cookie':'admin_web_session='+old})
        self.assertEqual(r.status_code,200);self.assertNotIn('set-cookie',r.headers)
        r=self.client.delete('/admin-web-session',headers={**self.headers(old),'Cookie':'admin_web_session='+new})
        self.assertEqual(r.status_code,200);self.assertNotIn('set-cookie',r.headers)
        self.assertEqual(self.client.post('/admin-web-session',headers=self.headers(old)).status_code,401)
        self.assertEqual(self.client.post('/admin-web-session',headers=self.headers(new)).status_code,200)
        r=self.client.delete('/admin-web-session',headers={'Cookie':'admin_web_session='+new})
        self.assertEqual(r.status_code,200);self.assertIn('Max-Age=0',r.headers['set-cookie'])
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'index.html').write_text('PRIVATE')
            self.client.app.mount('/fixture/web',AdminStaticFiles(directory=folder))
            with patch('src.server.web_access.SessionLocal',self.Session):
                r=self.client.get('/fixture/web/index.html',headers={'Cookie':'admin_web_session='+new},follow_redirects=False)
                self.assertEqual(r.status_code,303)

    def test_logout_does_not_require_email_confirmation_or_current_mfa(self):
        from src.modules.vehicle_hub.email_verification import EmailVerification
        user=self.register().json();token=user['access_token']
        with self.Session() as db:
            db.get(Customer,user['user']['id']).role='admin'
            db.get(EmailVerification,user['user']['id']).verified_at=None;db.commit()
        self.assertEqual(self.client.post('/user/logout',headers=self.headers(token)).status_code,204)
        self.assertEqual(self.client.get('/user/me',headers=self.headers(token)).status_code,401)

    def test_invalid_expired_and_forged_credentials_never_create_revocations(self):
        expired=create_access_token({'sub':'user@example.com'},expires_delta=timedelta(seconds=-5))
        ticket=decode_access_token_payload(create_access_token({'sub':'user@example.com'}))['logout_ticket']
        # Change a signed payload character, not a non-significant base64 padding bit.
        header,body,signature=ticket.split('.')
        forged=header+'.'+('x' if body[0]!='x' else 'y')+body[1:]+'.'+signature
        for token in ['invalid',expired]:
            self.assertEqual(self.client.post('/user/logout',headers=self.headers(token)).status_code,204)
        self.assertEqual(self.client.post('/user/logout').status_code,204)
        self.assertEqual(self.client.post('/user/logout',json={'logout_ticket':forged}).status_code,204)
        with self.Session() as db:self.assertEqual(db.query(RevokedAccessToken).count(),0)

    def test_store_failure_fails_closed_and_logout_is_not_reported_as_success(self):
        token=self.register().json()['access_token']
        RevokedAccessToken.__table__.drop(self.engine)
        for path in ['/test/protected','/fixture/optional']:
            r=self.client.get(path,headers=self.headers(token));self.assertEqual(r.status_code,503,r.text)
            self.assertNotIn(token,r.text);self.assertNotIn('SELECT',r.text)
        self.assertEqual(self.client.post('/user/logout',headers=self.headers(token)).status_code,503)
        self.assertEqual(self.client.delete('/admin-web-session',headers=self.headers(token)).status_code,503)

    def test_revocation_survives_new_engine_and_legacy_tokens_still_work(self):
        from src.core import security
        # Pre-upgrade bearer, deliberately no jti or logout_ticket.
        legacy=security.jwt.encode({'sub':'legacy@example.invalid','iat':datetime.utcnow(),'exp':datetime.utcnow()+timedelta(minutes=20)},security.JWT_SECRET_KEY,algorithm=security.JWT_ALGORITHM)
        with tempfile.TemporaryDirectory() as folder:
            url='sqlite:///'+folder+'/tokens.sqlite';engine=create_engine(url)
            RevokedAccessToken.__table__.create(engine)
            with sessionmaker(bind=engine)() as db:
                revoke_tokens(db,[legacy]);self.assertEqual(db.query(RevokedAccessToken).one().digest,hashlib.sha256(legacy.encode()).hexdigest())
            engine.dispose();engine=create_engine(url)
            with sessionmaker(bind=engine)() as db:
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as error:require_active_token(db,legacy)
                self.assertEqual(error.exception.status_code,401)
            engine.dispose()

    def test_cleanup_only_removes_expired_revocations(self):
        token=self.register().json()['access_token']
        with self.Session() as db:
            db.add(RevokedAccessToken(digest='0'*64,expires_at=datetime.utcnow()-timedelta(seconds=1)))
            db.add(RevokedAccessToken(digest='1'*64,expires_at=datetime.utcnow()+timedelta(hours=1)))
            db.commit();revoke_tokens(db,[token])
            self.assertEqual(set(db.scalars(select(RevokedAccessToken.digest))),{'1'*64,token_digest(token)})
