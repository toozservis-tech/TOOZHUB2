import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_account_flows as fixtures
from src.server.security_tracking import access_event_view, access_diagnostics
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog

class AccessHistory(unittest.TestCase):
    setUp = fixtures.AccountFlows.setUp
    tearDown = fixtures.AccountFlows.tearDown
    register = fixtures.AccountFlows.register
    verified_admin_token = fixtures.AccountFlows.verified_admin_token

    def test_history_is_admin_only_paginated_searchable_and_secret_free(self):
        account=self.register().json()
        headers={'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
        path='/admin-api/control-center/access-history'
        self.assertEqual(self.client.get(path,headers=headers).status_code,403)
        with self.Session() as db:
            db.get(Customer,account['user']['id']).role='admin'
            for i in range(3):
                db.add(SecurityAccessLog(user_email='review@example.com',event_type='login_failed',
                    user_agent='Example/13',created_at=datetime.utcnow()-timedelta(days=20,seconds=i),
                    details=json.dumps({'reason':'user_not_found','password':'DO-NOT-EXPOSE','token':'SECRET'})))
            db.commit()
        first=self.client.get(path+'?limit=2&search=review',headers=headers)
        self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(first.json()['total'],3)
        self.assertEqual(len(first.json()['items']),2)
        self.assertNotIn('DO-NOT-EXPOSE',first.text)
        self.assertNotIn('SECRET',first.text)
        self.assertEqual(first.json()['items'][0]['reason'],'user_not_found')
        self.assertTrue(first.json()['items'][0]['created_at'].endswith('+00:00'))
        second=self.client.get(path+'?limit=2&offset=2&search=review',headers=headers).json()
        self.assertEqual(len(second['items']),1)
        self.assertNotEqual(first.json()['items'][0]['id'],second['items'][0]['id'])
        self.assertEqual(self.client.get(path+'?search=%25',headers=headers).json()['total'],0)
        self.assertEqual(self.client.get(path+'?limit=10000',headers=headers).status_code,422)

    def test_untrusted_client_cannot_claim_server_or_inject_diagnostics(self):
        request=SimpleNamespace(headers={'x-app-build':'14','x-app-version':'1.0.0',
            'x-app-os':'secret\nAuthorization: stolen','x-server-environment':'sandbox'})
        with patch.dict('os.environ',{'SV_ISOLATED_APPLE_SANDBOX':'0'}):
            data=access_diagnostics(request)
        self.assertEqual(data['server_environment'],'production')
        self.assertEqual(data['app_build'],'14')
        self.assertNotIn('app_os',data)
        self.assertEqual(access_event_view(SimpleNamespace(details='[]',user_agent=None))['user_agent'],'')

    def test_account_overview_and_exact_stable_history(self):
        account = self.register().json()
        headers = {'Authorization': 'Bearer ' + self.verified_admin_token(account['user']['id'])}
        path = '/admin-api/control-center/access-accounts'
        self.assertEqual(self.client.get(path, headers=headers).status_code, 403)
        with self.Session() as db:
            db.get(Customer, account['user']['id']).role = 'admin'
            for i in range(55):
                db.add(SecurityAccessLog(user_email='one@example.com', event_type='login_success',
                    created_at=datetime(2026, 1, 1) + timedelta(seconds=i)))
            db.add(SecurityAccessLog(user_email='two@example.com', event_type='login_failed',
                created_at=datetime(2026, 1, 2)))
            db.add(SecurityAccessLog(user_email='one@example.com.evil', event_type='login_failed',
                created_at=datetime(2026, 1, 3)))
            db.commit()
        result = self.client.get(path+'?search=example.com', headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        one = next(r for r in result.json()['items'] if r['actor'] == 'one@example.com')
        self.assertEqual(one['event_count'], 55)
        self.assertEqual(one['created_at'], '2026-01-01T00:00:54+00:00')
        failed = self.client.get(path+'?failures=true', headers=headers).json()['items']
        self.assertNotIn('one@example.com', [r['actor'] for r in failed])
        hist='/admin-api/control-center/access-history?actor=one@example.com&limit=50'
        first=self.client.get(hist,headers=headers).json()
        self.assertEqual(first['total'],55)
        with self.Session() as db:
            db.add(SecurityAccessLog(user_email='one@example.com',event_type='login_success'))
            db.commit()
        second=self.client.get(hist+'&offset=50&before_id='+str(first['snapshot_id']),headers=headers).json()
        self.assertEqual(second['total'],55)
        self.assertEqual(len(second['items']),5)
        self.assertFalse(set(r['id'] for r in first['items']) & set(r['id'] for r in second['items']))
        self.assertEqual(self.client.get(path+'?role=other',headers=headers).status_code,422)
