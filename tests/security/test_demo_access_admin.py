from datetime import datetime, timedelta
from unittest.mock import patch
from test_public_demo import PublicDemoSecurity
from src.server.routers import public_demo as demo
from src.modules.vehicle_hub.models import Customer
from src.modules.email_client.service import EmailService

class DemoAccessAdmin(PublicDemoSecurity):
    def admin_headers(self):
        account=self.register('admin@example.com').json()
        with self.Session() as db:
            db.get(Customer,account['user']['id']).role='admin'; db.commit()
        return {'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
    def listing(self, headers, **params):
        return self.client.get('/admin-api/control-center/demo-access', headers=headers, params=params)
    def test_history_has_actual_send_and_verify_times_but_no_credentials(self):
        headers=self.admin_headers(); cid=self.issue()
        response=self.listing(headers); self.assertEqual(response.status_code,200,response.text)
        row=response.json()['items'][0]
        self.assertEqual(row['email'],'visitor@example.com');self.assertEqual(row['status'],'sent')
        self.assertTrue(row['sent_at']);self.assertIsNone(row['verified_at'])
        self.assertEqual(self.redeem(cid).status_code,200)
        response=self.listing(headers,status='verified');row=response.json()['items'][0]
        self.assertEqual(row['status'],'verified');self.assertTrue(row['verified_at']);self.assertEqual(row['attempts'],1)
        self.assertNotIn(cid,response.text);self.assertNotIn('123456',response.text)
        self.assertNotIn('digest',response.text);self.assertNotIn('hash',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        with self.Session() as db:
            db.query(demo.DemoChallenge).delete();db.commit()
        self.assertEqual(self.listing(headers).json()['total'],1)
    def test_no_anonymous_customer_service_or_demo_access(self):
        self.assertIn(self.listing({}).status_code,(401,403))
        account=self.register().json();headers={'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
        for role in ['user','service']:
            with self.Session() as db:
                db.get(Customer,account['user']['id']).role=role;db.commit()
            self.assertEqual(self.listing(headers).status_code,403)
        token=self.redeem(self.issue()).json()['access_token']
        self.assertEqual(self.listing({'Authorization':'Bearer '+token}).status_code,401)
    def test_failure_expiry_search_retention_and_paging(self):
        headers=self.admin_headers()
        with patch.object(EmailService,'send_simple_email',return_value=False):
            self.assertEqual(self.client.post('/public-demo/request-code',json={'email':'failure@example.com'}).status_code,503)
        cid=self.issue()
        with self.Session() as db:
            db.query(demo.DemoAccess).filter_by(email='visitor@example.com').update({'expires_at':datetime.utcnow()-timedelta(seconds=1)})
            db.add(demo.DemoAccess(challenge_hash='old',email='old@example.com',requested_at=datetime.utcnow()-timedelta(days=91),expires_at=datetime.utcnow()-timedelta(days=90),status='sent',attempts=0))
            db.commit()
        self.assertEqual(self.listing(headers,status='delivery_failed').json()['total'],1)
        self.assertEqual(self.listing(headers,status='expired').json()['total'],1)
        self.assertEqual(self.listing(headers,search='%').json()['total'],0)
        self.assertEqual(self.listing(headers,search='VISITOR').json()['total'],1)
        first=self.listing(headers,limit=1).json();second=self.listing(headers,limit=1,offset=1).json()
        self.assertEqual(first['total'],2);self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        with self.Session() as db: self.assertEqual(db.query(demo.DemoAccess).filter_by(email='old@example.com').count(),0)
    def test_resend_and_failed_attempts_are_not_success(self):
        headers=self.admin_headers();old=self.issue();new=self.issue()
        self.assertEqual(self.listing(headers,status='superseded').json()['total'],1)
        self.assertEqual(self.redeem(old).status_code,400)
        for _ in range(5): self.assertEqual(self.redeem(new,'000000').status_code,400)
        rows=self.listing(headers,status='locked').json()['items'];self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]['verified_at']);self.assertEqual(rows[0]['attempts'],5)
