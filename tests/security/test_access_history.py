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

    def test_problem_period_severity_and_drilldown_exclude_healthy_accounts(self):
        account = self.register().json()
        headers = {'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
        with self.Session() as db:
            db.get(Customer, account['user']['id']).role = 'admin'
            for actor, event, age in [('healthy@example.com','login_success',0), ('warning@example.com','login_failed',0), ('error@example.com','request_failed',0), ('error@example.com','request_completed',0), ('old@example.com','login_failed',72)]:
                db.add(SecurityAccessLog(user_email=actor,event_type=event,created_at=datetime.utcnow()-timedelta(hours=age)))
            db.commit()
        path = '/admin-api/control-center/access-accounts'
        rows = self.client.get(path+'?hours=24',headers=headers).json()['items']
        self.assertEqual({r['actor']:r['severity'] for r in rows}, {'healthy@example.com':'success','warning@example.com':'warning','error@example.com':'error'})
        rows = self.client.get(path+'?hours=24&failures=true',headers=headers).json()['items']
        self.assertEqual({r['actor'] for r in rows}, {'warning@example.com','error@example.com'})
        self.assertTrue(all(r['problem_count'] == 1 for r in rows))
        history = self.client.get('/admin-api/control-center/access-history?actor=error@example.com&hours=24&failures=true',headers=headers).json()
        self.assertEqual(history['total'],1)
        self.assertEqual(history['items'][0]['severity'],'error')
        all_history = self.client.get(path+'?hours=0&failures=true',headers=headers).json()
        self.assertIn('old@example.com',[r['actor'] for r in all_history['items']])

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
        for suffix in ('&before_id', '&before_id='):
            response = self.client.get(path+'?search=review'+suffix, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['total'], 3)
        for value in ('bad', '0', '-1'):
            self.assertEqual(self.client.get(path+'?before_id='+value, headers=headers).status_code, 422)
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

    def test_completed_requests_record_result_without_payload_or_query(self):
        from src.server.security_tracking import log_completed_activity
        request = SimpleNamespace(state=SimpleNamespace(activity_actor={
            'user_email':'user@example.com','customer_id':1,'tenant_id':1}),
            scope={'route':SimpleNamespace(path='/api/v1/vehicles/{vehicle_id}')},
            path_params={'vehicle_id':42,'token':'DO-NOT-STORE'},method='PUT')
        with patch('src.server.security_tracking.log_security_event') as log:
            log_completed_activity(request,422,15.6)
            event=log.call_args.kwargs
            self.assertEqual(event['event_type'],'request_failed')
            self.assertEqual(event['details']['status'],422)
            self.assertEqual(event['details']['resource'],'vehicle_id=42')
            self.assertEqual(event['endpoint'],'/api/v1/vehicles/{vehicle_id}')
            self.assertNotIn('DO-NOT-STORE',str(event['details']))
            log_completed_activity(request,200,8)
            self.assertEqual(log.call_args.kwargs['event_type'],'request_completed')
        request.state=SimpleNamespace()
        with patch('src.server.security_tracking.log_security_event') as log:
            log_completed_activity(request,401,1)
            log.assert_not_called()

    def test_activity_middleware_records_success_and_failure_outcomes(self):
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.testclient import TestClient
        from src.server.security_tracking import completed_activity_middleware
        app=FastAPI()
        app.middleware('http')(completed_activity_middleware)
        @app.get('/vehicle/{vehicle_id}')
        async def action(vehicle_id:int, request:Request):
            request.state.activity_actor={'user_email':'test@example.com'}
            if vehicle_id == 2:
                raise HTTPException(403,'Private detail must not be logged')
            return {'ok':True}
        with patch('src.server.security_tracking.log_security_event') as log:
            client=TestClient(app)
            self.assertEqual(client.get('/vehicle/1?token=secret').status_code,200)
            self.assertEqual(log.call_args.kwargs['details']['status'],200)
            self.assertEqual(client.get('/vehicle/2').status_code,403)
            self.assertEqual(log.call_args.kwargs['event_type'],'request_failed')
            self.assertNotIn('Private detail',str(log.call_args.kwargs['details']))
            self.assertEqual(log.call_args.kwargs['endpoint'],'/vehicle/{vehicle_id}')
