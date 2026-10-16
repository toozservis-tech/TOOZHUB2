import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import unittest

import test_account_flows as fixtures
from src.server import client_activity
from src.server.routers import user_security
from src.server.security_tracking import access_event_view
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog


class ClientActivityTests(unittest.TestCase):
    register = fixtures.AccountFlows.register
    verified_admin_token = fixtures.AccountFlows.verified_admin_token

    def setUp(self):
        fixtures.AccountFlows.setUp(self)
        self.client.app.include_router(user_security.router)
        self.audit_patch = patch.object(client_activity, 'AuditSessionLocal', self.Session)
        self.audit_patch.start()

    def tearDown(self):
        self.audit_patch.stop()
        fixtures.AccountFlows.tearDown(self)

    def event(self, code='action.vehicles.add'):
        return {'code': code, 'occurred_at': datetime.now(timezone.utc).isoformat()}

    def test_steps_persist_under_authenticated_actor_and_admin_can_filter_them(self):
        account = self.register().json()
        token = account['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        events = [self.event('screen.vehicles'), self.event()]
        response = self.client.post('/user/activity', json={'events': events}, headers=headers)
        self.assertEqual(response.status_code, 204, response.text)
        with self.Session() as db:
            rows = db.query(SecurityAccessLog).order_by(SecurityAccessLog.id).all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r.user_email == account['user']['email'] for r in rows))
            self.assertEqual(rows[0].customer_id, account['user']['id'])
            self.assertEqual(rows[0].event_type, 'client_screen')
            self.assertEqual(access_event_view(rows[1])['ui_label'], 'Klepl na Přidat vozidlo')
            db.add(SecurityAccessLog(user_email=account['user']['email'], event_type='request_failed'))
            db.get(Customer, account['user']['id']).role = 'admin'
            db.commit()
        headers = {'Authorization': 'Bearer ' + self.verified_admin_token(account['user']['id'])}
        path = '/admin-api/control-center/access-history?actor=' + account['user']['email']
        steps = self.client.get(path + '&kind=steps', headers=headers).json()
        self.assertEqual(steps['total'], 2)
        self.assertEqual(steps['items'][0]['ui_code'], 'action.vehicles.add')
        self.assertEqual(self.client.get(path + '&kind=requests', headers=headers).json()['total'], 1)
        self.assertEqual(self.client.get(path + '&failures=true', headers=headers).json()['total'], 1)
        self.assertEqual(self.client.get(path, headers=headers).json()['total'], 3)
        self.assertEqual(self.client.get(path + '&kind=invalid', headers=headers).status_code, 422)

    def test_no_anonymous_or_forged_identity_or_arbitrary_sensitive_payloads(self):
        self.assertIn(self.client.post('/user/activity', json={'events': [self.event()]}).status_code, (401,403))
        account = self.register().json()
        headers = {'Authorization': 'Bearer ' + account['access_token']}
        payloads = [
            {'events': [self.event()], 'user_email': 'other@example.com'},
            {'events': [{**self.event(), 'password': 'do-not-store'}]},
            {'events': [self.event('password=do-not-store')]},
            {'events': []}, {'events': [self.event()] * 21},
            {'events': [{**self.event(), 'occurred_at': (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}]},
        ]
        for payload in payloads:
            self.assertEqual(self.client.post('/user/activity', json=payload, headers=headers).status_code, 422)
        with self.Session() as db:
            self.assertEqual(db.query(SecurityAccessLog).count(), 0)
        self.assertEqual(self.client.get('/admin-api/control-center/access-history', headers=headers).status_code, 403)

    def test_account_budget_and_allowlisted_presentation(self):
        account = self.register().json()
        headers = {'Authorization': 'Bearer ' + account['access_token']}
        with patch.object(user_security, 'save_ui_events'):
            statuses = [self.client.post('/user/activity', json={'events':[self.event()]}, headers=headers).status_code for _ in range(21)]
        self.assertEqual(statuses[:20], [204]*20)
        self.assertEqual(statuses[-1], 429)
        item = SecurityAccessLog(event_type='client_action', details=json.dumps({'ui_code':{}, 'ui_label':'secret'}))
        self.assertNotIn('secret', json.dumps(access_event_view(item)))
