"""Browser authorization regressions, isolated database; no real mail."""
from unittest.mock import patch
from pathlib import Path
import tempfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_account_flows import AccountFlows
from src.server.web_access import router, AdminStaticFiles
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.database import get_db

class WebAccess(AccountFlows):
    def test_browser_gate_roles_and_revocation(self):
        user = self.register().json()
        self.client.app.include_router(router)
        token = user['access_token']; headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.post('/admin-web-session', headers=headers).status_code, 403)
        with self.Session() as db:
            row=db.get(Customer,user['user']['id']); row.role='admin'; db.commit()
        token=self.verified_admin_token(user['user']['id']);headers={'Authorization':'Bearer '+token}
        response=self.client.post('/admin-web-session',headers=headers)
        self.assertEqual(response.status_code,200)
        cookie=response.headers['set-cookie']
        for flag in ['HttpOnly','Secure','SameSite=strict']: self.assertIn(flag,cookie)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'index.html').write_text('PRIVATE DASHBOARD')
            Path(folder,'reset-password.html').write_text('PUBLIC RESET')
            self.client.app.mount('/web',AdminStaticFiles(directory=folder,html=True,public_pages={'reset-password.html'}))
            with patch('src.server.web_access.SessionLocal',self.Session):
                self.assertEqual(self.client.get('/web/index.html',follow_redirects=False).status_code,303)
                self.assertEqual(self.client.get('/web/reset-password.html').status_code,200)
                h={'Cookie':'admin_web_session='+token}
                self.assertEqual(self.client.get('/web/index.html',headers=h).text,'PRIVATE DASHBOARD')
                with self.Session() as db:
                    row=db.get(Customer,user['user']['id']); row.role='user'; db.commit()
                self.assertEqual(self.client.get('/web/index.html',headers=h).status_code,403)
                self.assertEqual(self.client.get('/web/index.html',headers={'Cookie':'admin_web_session=invalid'},follow_redirects=False).status_code,303)
        self.assertEqual(self.client.delete('/admin-web-session').status_code,200)
    def test_reset_page_returns_to_app_without_token(self):
        html=self.client.get('/reset-password.html').text
        self.assertIn('spravavozidel://login',html)
        self.assertNotIn('/web/index.html',html)
        self.assertNotIn('window.location.href',html)
