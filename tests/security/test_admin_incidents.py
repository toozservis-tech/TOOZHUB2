"""Real auth/API/SQLite incident lifecycle. No production writes or external mail."""
import json
from uuid import uuid4
from datetime import datetime
import unittest
from unittest.mock import patch
import test_account_flows as fixtures
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog, DeveloperActionAuditLog, License
from src.modules.vehicle_hub.admin_incident_models import AdminIncident, AdminIncidentHistory, AdminIncidentEvent
from src.core.security import create_access_token
from src.server.admin_incidents import safe_endpoint

BASE='/admin-api/control-center/incidents'

class Incidents(unittest.TestCase):
    tearDown=fixtures.AccountFlows.tearDown
    register=fixtures.AccountFlows.register
    verified_admin_token=fixtures.AccountFlows.verified_admin_token
    def setUp(self):
        fixtures.AccountFlows.setUp(self)
        self.account=self.register('admin@example.com').json()
        self.user=self.register('private.person@example.com').json()
        with self.Session() as db:
            db.get(Customer,self.account['user']['id']).role='admin';db.commit()
        self.headers={'Authorization':'Bearer '+self.verified_admin_token(self.account['user']['id'])}
        self.event=self.seed()
    def seed(self,**changes):
        data=dict(customer_id=self.user['user']['id'],user_email='private.person@example.com',ip_address='198.51.100.7',
                  endpoint='/analytics/monthly-costs',event_type='request_failed',user_agent='secret-device',
                  details=json.dumps({'status':403,'app_version':'1.0.7','app_build':'56','client_platform':'ios','server_environment':'production','reason':'private secret','token':'SECRET_TOKEN','resource':'VIN123456789012345'}))
        data.update(changes)
        with self.Session() as db:
            row=SecurityAccessLog(**data);db.add(row);db.commit();return row.id
    def create(self,event=None):
        response=self.client.post(BASE+f'/from-event/{event or self.event}',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);return response.json()
    def command(self,case,status,note='',**changes):
        body={'status':status,'note':note,'expected_version':case['version'],'client_id':str(uuid4())};body.update(changes)
        return self.client.post(BASE+f'/{case["id"]}/transition',headers=self.headers,json=body)

    def test_role_assurance_and_cross_origin_rejected(self):
        for headers in ({},{'Authorization':'Bearer '+self.user['access_token']},{'Authorization':'Bearer '+create_access_token({'sub':'admin@example.com'})}):
            for method,path in [('get',BASE),('post',BASE+f'/from-event/{self.event}'),('get',BASE+'/1/diagnostic'),('get',BASE+'/1/check')]:
                self.assertIn(getattr(self.client,method)(path,headers=headers).status_code,(401,403))
        with self.Session() as db:db.get(Customer,self.user['user']['id']).role='service';db.commit()
        self.assertEqual(self.client.get(BASE,headers={'Authorization':'Bearer '+self.user['access_token']}).status_code,403)
        for extra in ({'Origin':'https://evil.example'},{'Origin':'null'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.client.post(BASE+f'/from-event/{self.event}',headers={**self.headers,**extra}).status_code,403)
        self.assertEqual(self.client.post(BASE+f'/from-event/{self.event}',headers={**self.headers,'Origin':'http://testserver'}).status_code,200)

    def test_case_lifecycle_idempotency_versions_audit_and_original_history(self):
        case=self.create();self.assertEqual(case['status'],'open')
        self.assertEqual(self.create()['id'],case['id'])
        body={'expected_version':case['version'],'client_id':str(uuid4()),'status':'in_progress','note':'Prověřuji situaci'}
        url=BASE+f'/{case["id"]}/transition'
        first=self.client.post(url,headers=self.headers,json=body);self.assertEqual(first.status_code,200,first.text)
        self.assertEqual(self.client.post(url,headers=self.headers,json=body).json()['version'],2)
        self.assertEqual(self.client.post(url,headers=self.headers,json={**body,'note':'Jiný obsah'}).status_code,409)
        self.assertEqual(self.command(case,'dismissed','Druhý správce se starou verzí').status_code,409)
        case=first.json();self.assertEqual(self.command(case,'resolved').status_code,422)
        resolved=self.command(case,'resolved','Oprava ověřena skutečným opakováním kroku').json()
        self.assertEqual(resolved['status'],'resolved');self.assertEqual(self.create()['status'],'resolved')
        self.assertEqual(self.command(resolved,'open').status_code,422)
        reopened=self.command(resolved,'open','Uživatel chybu zopakoval').json();self.assertEqual(reopened['status'],'open')
        note={'expected_version':reopened['version'],'client_id':str(uuid4()),'note':'Poznámka s původním výsledkem'}
        response=self.client.post(BASE+f'/{case["id"]}/notes',headers=self.headers,json=note)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()['history']),5)
        with self.Session() as db:
            self.assertEqual(db.query(SecurityAccessLog).count(),1)
            self.assertEqual(json.loads(db.get(SecurityAccessLog,self.event).details)['reason'],'private secret')
            self.assertEqual(db.query(AdminIncident).count(),1)
            self.assertEqual(db.query(AdminIncidentHistory).count(),5)
            self.assertEqual(db.query(DeveloperActionAuditLog).filter(DeveloperActionAuditLog.action_type.like('incident.%')).count(),5)
        history=self.client.get('/admin-api/control-center/access-history',headers=self.headers).json()['items'][0]
        self.assertEqual(history['severity'],'error');self.assertEqual(history['incident']['status'],'open')

    def test_recurrences_and_resolved_case_remain_distinct_from_error_counts(self):
        first=self.create();second=self.create(self.seed())
        self.assertEqual(first['id'],second['id']);self.assertEqual(second['recurrence_count'],2)
        closed=self.command(second,'dismissed','Záměrné omezení tarifu ověřeno').json()
        self.assertEqual(self.client.get(BASE,headers=self.headers).json()['total'],0)
        following=self.create(self.seed());self.assertNotEqual(following['id'],closed['id'])
        # An active recurrence must be investigated before another case is reopened.
        self.assertEqual(self.command(closed,'open','Chci znovu prošetřit').status_code,409)
        self.assertEqual(self.client.get(BASE+'?status=all',headers=self.headers).json()['total'],2)
        accounts=self.client.get('/admin-api/control-center/access-accounts',headers=self.headers).json()['items']
        self.assertEqual(accounts[0]['error_count'],3);self.assertEqual(accounts[0]['unresolved_incident_count'],1)

    def test_diagnostic_strict_allowlist_and_read_only_recheck(self):
        bad='/vehicles/42/private.person@example.com/VIN123456789012345?token=SECRET_TOKEN'
        case=self.create(self.seed(endpoint=bad,details=json.dumps({'status':500,'app_version':'secret email','app_build':'SECRET_TOKEN','server_environment':'private.host','client_platform':'ios secret','headers':{'Authorization':'Bearer SECRET_TOKEN'}})))
        url=BASE+f'/{case["id"]}'
        self.command(case,'in_progress','Private person phone +420777123456 and password SECRET_TOKEN')
        result=self.client.get(url+'/diagnostic',headers=self.headers)
        self.assertEqual(result.headers['cache-control'],'no-store');self.assertTrue(result.json()['redacted'])
        for secret in ('private.person','198.51.100','VIN123','SECRET_TOKEN','+420777','private.host','secret-device','secret email'):
            self.assertNotIn(secret,result.text)
        self.assertIn('/vehicles/{id}/{redacted}/{redacted}',result.text)
        with self.Session() as db:
            before=[db.query(model).count() for model in (License,AdminIncident,AdminIncidentHistory,SecurityAccessLog,DeveloperActionAuditLog)]
        with patch('src.modules.licensing.service.get_or_create_license',side_effect=AssertionError('read only')):
            checked=self.client.get(url+'/check',headers=self.headers)
        self.assertEqual(checked.status_code,200,checked.text);self.assertEqual(checked.json()['diagnosis']['code'],'server_error')
        with self.Session() as db:self.assertEqual(before,[db.query(model).count() for model in (License,AdminIncident,AdminIncidentHistory,SecurityAccessLog,DeveloperActionAuditLog)])

    def test_no_automatic_403_resolution_and_no_unknown_command(self):
        case=self.create();self.assertEqual(case['diagnosis']['code'],'current_restriction_possible');self.assertEqual(case['status'],'open')
        unknown=self.create(self.seed(endpoint='/admin-api/control-center/health'))
        self.assertEqual(unknown['diagnosis']['code'],'access_denied_unexplained')
        self.assertEqual(self.client.post(BASE+f'/{case["id"]}/repair',headers=self.headers,json={'url':'/license/grant','plan':'premium'}).status_code,404)
        self.assertEqual(self.command(case,'resolved','Valid note',grant_premium=True).status_code,422)
        healthy=self.seed(event_type='request_completed')
        self.assertEqual(self.client.post(BASE+f'/from-event/{healthy}',headers=self.headers).status_code,422)
        self.assertEqual(self.client.get(BASE+'?status=everything',headers=self.headers).status_code,422)
        self.assertEqual(self.client.get(BASE+'?search=%25',headers=self.headers).json()['total'],0)

    def test_migration_repeatable_and_missing_schema_does_not_erase_history(self):
        from scripts.migrate_admin_incidents import migrate_connection
        from src.modules.vehicle_hub.admin_incident_models import TABLES
        with self.engine.begin() as conn:
            for table in reversed(TABLES):table.drop(conn)
        self.assertEqual(self.client.get(BASE,headers=self.headers).status_code,503)
        self.assertEqual(self.client.get('/admin-api/control-center/access-history',headers=self.headers).json()['total'],1)
        with self.engine.begin() as conn:migrate_connection(conn);migrate_connection(conn)
        self.assertEqual(self.create()['status'],'open')

    def test_inactive_account_denied_even_with_valid_admin_token(self):
        with self.Session() as db:
            db.get(Customer,self.account['user']['id']).is_disabled=True;db.commit()
        self.assertEqual(self.client.get(BASE,headers=self.headers).status_code,401)

    def test_recheck_does_not_reactivate_inactive_license_with_reward(self):
        from src.modules.vehicle_hub.referrals import ReferralReward
        with self.Session() as db:
            customer=db.get(Customer,self.user['user']['id'])
            license=db.query(License).filter_by(tenant_id=customer.tenant_id).one();license.status='inactive'
            db.add(ReferralReward(customer_id=customer.id,source='admin',ordinal=1,starts_at=datetime(2020,1,1),ends_at=None,reason='Fixture',waiting_for_paid=False));db.commit()
        case=self.create()
        self.assertEqual(case['diagnosis']['code'],'current_restriction_possible')
        self.assertEqual(next(c for c in case['checks'] if c['code']=='license')['state'],'warning')

    def test_pagination_preserves_full_notes_and_resources_are_not_grouped(self):
        case=self.create(self.seed(endpoint='/api/v1/vehicles/{vehicle_id}',details='{"status":403,"resource":"vehicle_id=1"}'))
        other=self.create(self.seed(endpoint='/api/v1/vehicles/{vehicle_id}',details='{"status":403,"resource":"vehicle_id=2"}'))
        self.assertNotEqual(case['id'],other['id'])
        with self.Session() as db:
            for i in range(205):db.add(AdminIncidentHistory(incident_id=case['id'],admin_id=self.account['user']['id'],action='note',status='open',note='Fixture note '+str(i),version=1))
            db.commit()
        detail=self.client.get(BASE+f'/{case["id"]}',headers=self.headers).json()
        self.assertEqual(detail['history_total'],206);self.assertTrue(detail['history_truncated'])
        first=self.client.get(BASE+f'/{case["id"]}/history?limit=200',headers=self.headers).json()
        second=self.client.get(BASE+f'/{case["id"]}/history?offset=200&limit=200',headers=self.headers).json()
        self.assertEqual(len(first['items'])+len(second['items']),206)
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        self.assertEqual(self.client.get(BASE+f'/{case["id"]}/history?limit=201',headers=self.headers).status_code,422)
        events=self.client.get(BASE+f'/{case["id"]}/events',headers=self.headers).json()
        self.assertEqual(events['total'],1)

    def test_same_origin_proxy_configuration_is_explicit_not_arbitrary_header(self):
        with patch('src.server.admin_incidents.ALLOWED_ORIGINS',['https://app.example.com']):
            self.assertEqual(self.client.post(BASE+f'/from-event/{self.event}',headers={**self.headers,'Origin':'https://app.example.com'}).status_code,200)
            self.assertEqual(self.client.post(BASE+f'/from-event/{self.event}',headers={**self.headers,'Origin':'https://evil.example','X-Forwarded-Proto':'https','X-Forwarded-Host':'evil.example'}).status_code,403)

    def test_export_bounds_context_and_rejects_free_text_steps_and_metadata(self):
        from datetime import timedelta
        from src.server.client_activity import UI_ACTIONS
        now=datetime.utcnow()
        known_code=next(iter(UI_ACTIONS))
        self.seed(event_type='client_screen',created_at=now-timedelta(minutes=16),endpoint='/old',details=json.dumps({'ui_code':known_code,'ui_label':'OLD PRIVATE'}))
        self.seed(event_type='client_screen',created_at=now-timedelta(minutes=2),details=json.dumps({'ui_code':'unrecognized','ui_label':'PRIVATE UNKNOWN STEP'}))
        self.seed(event_type='client_action',created_at=now-timedelta(minutes=1),details=json.dumps({'ui_code':known_code,'ui_label':'PRIVATE LABEL','password':'SECRET_TOKEN'}))
        self.seed(created_at=now-timedelta(seconds=30),endpoint='/vehicles/123/private.person@example.com?secret=SECRET_TOKEN',details=json.dumps({'status':500,'reason':'PRIVATE REASON'}))
        case=self.create(self.seed(created_at=now,details=json.dumps({'status':403,'app_os':'iOS 27.0.1'})))
        text=self.client.get(BASE+f'/{case["id"]}/diagnostic',headers=self.headers).json()['text']
        self.assertIn('iOS 27.0.1',text);self.assertIn(UI_ACTIONS[known_code],text)
        self.assertIn('krok hlášený aplikací',text);self.assertIn('výsledek zaznamenaný serverem',text)
        for private in ('PRIVATE','SECRET_TOKEN','private.person','/old') :self.assertNotIn(private,text)
        self.assertLessEqual(text.count('zaznamenaný serverem')+text.count('krok hlášený aplikací'),10)

    def test_real_analytics_policy_requires_premium_but_preserves_role_access(self):
        from src.modules.vehicle_hub.routers_v1 import analytics
        self.client.app.include_router(analytics.router,prefix='/api/v1')
        user_headers={'Authorization':'Bearer '+self.user['access_token']}
        for plan in ('free','basic','premium'):
            with self.Session() as db:
                user=db.get(Customer,self.user['user']['id']);db.query(License).filter_by(tenant_id=user.tenant_id).one().plan=plan;db.commit()
            for endpoint in ('summary','monthly-costs','categories'):
                response=self.client.get('/api/v1/analytics/'+endpoint,headers=user_headers)
                self.assertEqual(response.status_code,200 if plan=='premium' else 403,response.text)
        with self.Session() as db:
            user=db.get(Customer,self.user['user']['id']);user.role='service';db.query(License).filter_by(tenant_id=user.tenant_id).one().plan='free';db.commit()
        self.assertEqual(self.client.get('/api/v1/analytics/summary',headers=user_headers).status_code,200)
        self.assertEqual(self.client.get('/api/v1/analytics/summary',headers=self.headers).status_code,200)

    def test_customer_facing_case_titles_describe_area_without_raw_protocol(self):
        from src.server.admin_incidents import incident_title
        from types import SimpleNamespace
        monthly=SimpleNamespace(endpoint='/api/v1/analytics/monthly-costs',event_type='request_failed',details='{"status":403}')
        self.assertEqual(incident_title(monthly),'Odepřený přístup · Měsíční náklady')
        monthly.endpoint='/api/v1/analytics/summary'
        self.assertEqual(incident_title(monthly),'Odepřený přístup · Statistiky')
        monthly.endpoint='/unknown/private.person@example.com'
        self.assertEqual(incident_title(monthly),'Odepřený přístup · Požadavek aplikace')
