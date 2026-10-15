from datetime import datetime, timedelta
from unittest.mock import patch
from test_account_flows import AccountFlows
from src.server.routers import public_demo as demo
from src.modules.email_client.service import EmailService

class PublicDemoSecurity(AccountFlows):
    def setUp(self):
        super().setUp()
        self.client.app.include_router(demo.router)
    def issue(self):
        with patch.object(demo.secrets, 'randbelow', return_value=123456), patch.object(EmailService, 'send_simple_email', return_value=True) as mail:
            r=self.client.post('/public-demo/request-code',json={'email':'visitor@example.com'})
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn('123456',mail.call_args.kwargs['body'])
            self.assertNotIn('123456',r.text)
            return r.json()['challenge_id']
    def redeem(self, challenge, code='123456'):
        return self.client.post('/public-demo/verify-code',json={'challenge_id':challenge,'code':code})
    def test_single_use_and_customer_isolation(self):
        cid=self.issue(); r=self.redeem(cid); self.assertEqual(r.status_code,200,r.text)
        token=r.json()['access_token']; headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.get('/public-demo/content',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/test/protected',headers=headers).status_code,401)
        self.assertEqual(self.client.put('/user/me',json={'name':'overwrite'},headers=headers).status_code,401)
        self.assertEqual(self.client.post('/public-demo/content',json={},headers=headers).status_code,405)
        self.assertEqual(self.redeem(cid).status_code,400)
    def test_attempt_budget(self):
        cid=self.issue()
        for _ in range(5): self.assertEqual(self.redeem(cid,'999999').status_code,400)
        self.assertEqual(self.redeem(cid).status_code,400)
    def test_expiry_and_resend(self):
        old=self.issue(); new=self.issue()
        self.assertEqual(self.redeem(old).status_code,400)
        with self.Session() as db:
            db.get(demo.DemoChallenge,new).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
        self.assertEqual(self.redeem(new).status_code,400)
    def test_delivery_failure_and_rate_limit(self):
        with patch.object(EmailService,'send_simple_email',return_value=False):
            self.assertEqual(self.client.post('/public-demo/request-code',json={'email':'visitor@example.com'}).status_code,503)
        self.issue();self.issue()
        self.assertEqual(self.client.post('/public-demo/request-code',json={'email':'visitor@example.com'}).status_code,429)
    def test_missing_invalid_customer_and_expired_tokens_denied(self):
        self.assertIn(self.client.get('/public-demo/content').status_code,(401,403))
        customer=self.register().json()['access_token']
        expired=demo.jwt.encode({'aud':'public-demo','scope':'demo:read','exp':datetime.utcnow()-timedelta(seconds=1)},demo._KEY,algorithm='HS256')
        for token in ('bad',customer,expired):
            self.assertEqual(self.client.get('/public-demo/content',headers={'Authorization':'Bearer '+token}).status_code,401)
    def test_no_plain_email_or_code_in_database(self):
        cid=self.issue()
        with self.Session() as db:
            row=db.get(demo.DemoChallenge,cid)
            self.assertNotIn('visitor',row.email_hash)
            self.assertNotEqual(row.digest,'123456')
