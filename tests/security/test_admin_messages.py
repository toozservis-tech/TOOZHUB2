"""Authenticated individual conversations; no production delivery or external service."""
import json
from uuid import uuid4
from datetime import datetime
from unittest.mock import patch
import unittest
import test_account_flows as fixtures
from src.core.security import create_access_token
from src.modules.vehicle_hub.models import Customer,DeveloperActionAuditLog
from src.modules.vehicle_hub.admin_message_models import AdminMessage,AdminMessageCommand,TABLES
from src.server.admin_messages import recipient_router

ADMIN='/admin-api/control-center/messages'
OWN='/api/v1/admin-messages'

class Messages(unittest.TestCase):
    tearDown=fixtures.AccountFlows.tearDown
    register=fixtures.AccountFlows.register
    verified_admin_token=fixtures.AccountFlows.verified_admin_token
    def setUp(self):
        fixtures.AccountFlows.setUp(self)
        self.client.app.include_router(recipient_router,prefix='/api/v1')
        self.admin=self.register('admin@example.com').json();self.user=self.register('user@example.com').json();self.other=self.register('other@example.com').json()
        self.service=self.register('service@example.com').json()
        with self.Session() as db:
            db.get(Customer,self.admin['user']['id']).role='admin';db.get(Customer,self.service['user']['id']).role='service';db.commit()
        self.ah={'Authorization':'Bearer '+self.verified_admin_token(self.admin['user']['id'])}
        self.uh={'Authorization':'Bearer '+self.user['access_token']};self.oh={'Authorization':'Bearer '+self.other['access_token']};self.sh={'Authorization':'Bearer '+self.service['access_token']}
        patcher=patch('src.modules.vehicle_hub.routers_v1.auth.log_user_activity');patcher.start();self.patches.append(patcher)
    def path(self,account=None):return ADMIN+f'/accounts/{(account or self.user)["user"]["id"]}'
    def send(self,ack=False,account=None,body='Soukromá zpráva',client_id=None):
        response=self.client.post(self.path(account),headers=self.ah,json={'body':body,'requires_ack':ack,'client_id':client_id or str(uuid4())})
        self.assertEqual(response.status_code,200,response.text);return response.json()['message']
    def read(self,ids,headers=None,client_id=None,path=OWN+'/read'):
        return self.client.post(path,headers=headers or self.uh,json={'message_ids':ids,'client_id':client_id or str(uuid4())})
    def ack(self,identity,headers=None,client_id=None):
        return self.client.post(OWN+f'/{identity}/ack',headers=headers or self.uh,json={'client_id':client_id or str(uuid4())})
    def reply(self,headers=None,body='Odpověď příjemce'):
        response=self.client.post(OWN,headers=headers or self.uh,json={'body':body,'client_id':str(uuid4())})
        self.assertEqual(response.status_code,200,response.text);return response.json()['message']

    def test_read_is_not_ack_and_ordinary_banner_clears_but_required_persists(self):
        ordinary=self.send();required=self.send(True)
        self.assertEqual(self.client.get(OWN+'/summary',headers=self.uh).json()['banner_count'],2)
        before=self.client.get(OWN,headers=self.uh)
        self.assertEqual(before.headers['cache-control'],'no-store')
        self.assertTrue(all(item['read_at'] is None for item in before.json()['items']))
        read=self.read([ordinary['id'],required['id']]);self.assertEqual(read.status_code,200,read.text)
        self.assertEqual(read.json()['summary']['unread_count'],0);self.assertEqual(read.json()['summary']['pending_ack_count'],1)
        self.assertEqual(read.json()['summary']['banner_count'],1)
        self.assertEqual(len(read.json()['items']),2);self.assertTrue(all(item['read_at'] for item in read.json()['items']))
        self.assertIsNone(read.json()['items'][1]['acknowledged_at'])
        ack=self.ack(required['id']);self.assertEqual(ack.status_code,200,ack.text)
        self.assertEqual(ack.json()['summary']['banner_count'],0)
        self.assertTrue(ack.json()['message']['acknowledged_at'])
        again=self.ack(required['id']);self.assertEqual(again.json()['message']['acknowledged_at'],ack.json()['message']['acknowledged_at'])
        with self.Session() as db:self.assertEqual(db.query(AdminMessage).count(),2)

    def test_reply_and_admin_receipt_are_scoped_to_incoming_actual_ids(self):
        outbound=self.send(True)
        one=self.reply();two=self.reply(body='Pozdější odpověď')
        self.assertEqual(one['sender_kind'],'recipient');self.assertFalse(one['requires_ack'])
        inbox=self.client.get(ADMIN,headers=self.ah).json()
        self.assertEqual(inbox['items'][0]['unread_admin_count'],2)
        self.assertEqual(self.read([outbound['id']],headers=self.ah,path=self.path()+'/read').status_code,403)
        result=self.read([one['id']],headers=self.ah,path=self.path()+'/read')
        self.assertEqual(result.json()['summary']['unread_admin_count'],1)
        detail=self.client.get(self.path(),headers=self.ah).json()['items']
        self.assertTrue(next(m for m in detail if m['id']==one['id'])['read_at'])
        self.assertIsNone(next(m for m in detail if m['id']==two['id'])['read_at'])
        self.assertIsNone(next(m for m in detail if m['id']==outbound['id'])['acknowledged_at'])

    def test_new_incoming_message_is_not_marked_by_old_visible_ids(self):
        shown=self.send();newer=self.send(True)
        read=self.read([shown['id']]);self.assertEqual(read.status_code,200)
        self.assertEqual(read.json()['summary']['banner_count'],1)
        history=self.client.get(OWN,headers=self.uh).json()['items']
        self.assertIsNone(next(m for m in history if m['id']==newer['id'])['read_at'])
        self.assertIsNone(next(m for m in history if m['id']==newer['id'])['acknowledged_at'])

    def test_other_recipient_sender_spoof_and_admin_self_ack_denied(self):
        msg=self.send(True)
        self.assertEqual(self.read([msg['id']],headers=self.oh).status_code,403)
        self.assertEqual(self.ack(msg['id'],headers=self.oh).status_code,403)
        self.assertEqual(self.client.get(OWN,headers=self.oh).json()['items'],[])
        self.assertEqual(self.client.get(OWN+'?customer_id='+str(self.user['user']['id']),headers=self.oh).json()['items'],[])
        for headers in (self.uh,self.oh,self.sh):self.assertEqual(self.client.get(ADMIN,headers=headers).status_code,403)
        self.assertEqual(self.client.get(OWN,headers=self.ah).status_code,403)
        self.assertEqual(self.ack(msg['id'],headers=self.ah).status_code,403)
        spoof=self.client.post(OWN,headers=self.uh,json={'body':'X','client_id':str(uuid4()),'sender_kind':'admin','recipient_id':self.other['user']['id'],'requires_ack':True})
        self.assertEqual(spoof.status_code,422)
        ordinary=self.send(False);self.assertEqual(self.ack(ordinary['id']).status_code,403)
        mine=self.reply();self.assertEqual(self.read([mine['id']]).status_code,403);self.assertEqual(self.ack(mine['id']).status_code,403)
        with self.Session() as db:self.assertIsNone(db.get(AdminMessage,msg['id']).read_at)

    def test_commands_idempotent_and_conflicting_uuid_rejected(self):
        identity=str(uuid4());one=self.send(True,client_id=identity);two=self.send(True,client_id=identity)
        self.assertEqual(one['id'],two['id'])
        changed=self.client.post(self.path(),headers=self.ah,json={'body':'Different','requires_ack':True,'client_id':identity})
        self.assertEqual(changed.status_code,409)
        read_id=str(uuid4());first=self.read([one['id']],client_id=read_id);again=self.read([one['id']],client_id=read_id)
        self.assertEqual(first.json()['items'],again.json()['items']);self.assertEqual(first.json()['updated_count'],again.json()['updated_count'])
        self.assertEqual(self.ack(one['id'],client_id=read_id).status_code,409)
        ack_id=str(uuid4());ack=self.ack(one['id'],client_id=ack_id);repeat=self.ack(one['id'],client_id=ack_id)
        self.assertEqual(ack.json()['message'],repeat.json()['message'])
        with self.Session() as db:self.assertEqual(db.query(AdminMessage).count(),1);self.assertEqual(db.query(AdminMessageCommand).count(),3)

    def test_service_conversation_and_pending_filter_find_old_required_message(self):
        required=self.send(True,account=self.service)
        self.read([required['id']],headers=self.sh)
        for i in range(5):
            new=self.send(account=self.service,body=f'Běžná zpráva {i}');self.read([new['id']],headers=self.sh)
        recent=self.client.get(OWN+'?limit=2',headers=self.sh).json();self.assertNotIn(required['id'],[m['id'] for m in recent['items']])
        pending=self.client.get(OWN+'?limit=2&pending_only=true',headers=self.sh).json()
        self.assertEqual([m['id'] for m in pending['items']],[required['id']])
        self.reply(headers=self.sh)
        self.assertEqual(self.ack(required['id'],headers=self.sh).status_code,200)
        self.assertEqual(self.client.get(OWN+'?pending_only=true',headers=self.sh).json()['items'],[])

    def test_pagination_does_not_skip_when_new_message_arrives(self):
        messages=[self.send(body=f'Historie {i}') for i in range(8)]
        page1=self.client.get(OWN+'?limit=3',headers=self.uh).json();self.assertEqual([m['id'] for m in page1['items']],[m['id'] for m in messages[-3:]])
        self.send(body='Nová zpráva během stránkování')
        page2=self.client.get(OWN+f'?limit=3&before_id={page1["next_before_id"]}',headers=self.uh).json()
        page3=self.client.get(OWN+f'?limit=3&before_id={page2["next_before_id"]}',headers=self.uh).json()
        self.assertEqual(sorted([m['id'] for p in (page1,page2,page3) for m in p['items']]),[m['id'] for m in messages])
        self.assertFalse(page3['has_more'])
        self.assertEqual(self.client.get(OWN+'?limit=101',headers=self.uh).status_code,422)

    def test_auth_assurance_csrf_and_disabled_recipient(self):
        for headers in ({},{'Authorization':'Bearer '+create_access_token({'sub':'admin@example.com'})}):
            self.assertIn(self.client.get(ADMIN,headers=headers).status_code,(401,403))
        body={'body':'Do not deliver','client_id':str(uuid4())}
        for headers,path in ((self.ah,self.path()),(self.uh,OWN)):
            for extra in ({'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'},{'Origin':'null'}):
                self.assertEqual(self.client.post(path,headers={**headers,**extra},json=body).status_code,403)
        with self.Session() as db:db.get(Customer,self.user['user']['id']).is_disabled=True;db.commit()
        self.assertEqual(self.client.post(self.path(),headers=self.ah,json=body).status_code,409)
        self.assertEqual(self.client.get(OWN,headers=self.uh).status_code,401)
        self.assertEqual(self.client.get(self.path(),headers=self.ah).status_code,200)

    def test_body_limits_extra_read_fields_and_audit_excludes_private_body(self):
        for value in ('','   ','x'*4001,'abc\u0000'):
            self.assertEqual(self.client.post(self.path(),headers=self.ah,json={'body':value,'client_id':str(uuid4())}).status_code,422)
        msg=self.send(body='SECRET_PRIVATE_MESSAGE 123456 private@example.com')
        response=self.client.post(OWN+'/read',headers=self.uh,json={'through_id':msg['id'],'client_id':str(uuid4())})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.read([]).status_code,422)
        self.assertEqual(self.read([0]).status_code,422)
        self.assertEqual(self.read([msg['id']]*101).status_code,422)
        with self.Session() as db:
            audit=' '.join(row.parameters_json or '' for row in db.query(DeveloperActionAuditLog))
            self.assertNotIn('SECRET_PRIVATE_MESSAGE',audit);self.assertNotIn('private@example.com',audit)
            commands=' '.join(row.message_ids_json or '' for row in db.query(AdminMessageCommand))
            self.assertNotIn('SECRET_PRIVATE_MESSAGE',commands)
        self.assertEqual(self.client.delete(self.path(),headers=self.ah).status_code,405)

    def test_schema_missing_fails_closed_and_migration_preserves_receipts(self):
        from scripts.migrate_admin_messages import migrate_connection
        with self.engine.begin() as connection:
            for table in reversed(TABLES):table.drop(connection)
        self.assertEqual(self.client.get(OWN+'/summary',headers=self.uh).status_code,503)
        self.assertEqual(self.client.get(ADMIN,headers=self.ah).status_code,503)
        with self.engine.begin() as connection:migrate_connection(connection);migrate_connection(connection)
        message=self.send(True);result=self.ack(message['id'])
        with self.engine.begin() as connection:migrate_connection(connection);migrate_connection(connection)
        current=self.client.get(OWN,headers=self.uh).json()['items'][0]
        self.assertEqual(current['acknowledged_at'],result.json()['message']['acknowledged_at'])

    def test_public_demo_token_and_unverified_email_cannot_access_private_messages(self):
        from src.server.routers.public_demo import _KEY
        import jwt
        from datetime import timedelta
        token=jwt.encode({'aud':'public-demo','scope':'demo:read','iat':datetime.utcnow(),
            'exp':datetime.utcnow()+timedelta(hours=1)},_KEY,algorithm='HS256')
        headers={'Authorization':'Bearer '+token}
        for path in (OWN,OWN+'/summary',ADMIN,self.path()):
            self.assertEqual(self.client.get(path,headers=headers).status_code,401)
        self.assertEqual(self.client.post(OWN,headers=headers,json={'body':'Do not send','client_id':str(uuid4())}).status_code,401)
        from src.modules.vehicle_hub.email_verification import EmailVerification
        with self.Session() as db:
            db.get(EmailVerification,self.user['user']['id']).verified_at=None;db.commit()
        self.assertEqual(self.client.get(OWN,headers=self.uh).status_code,403)
        self.assertEqual(self.client.post(OWN,headers=self.uh,json={'body':'Do not send','client_id':str(uuid4())}).status_code,403)

    def test_account_erasure_foreign_keys_preserves_other_conversation(self):
        from src.modules.vehicle_hub.account_erasure import erase_account
        from sqlalchemy import text
        erased=self.send(True);self.read([erased['id']]);self.ack(erased['id']);self.reply()
        retained=self.send(True,account=self.other,body='Other private message')
        with self.engine.connect() as connection:connection.execute(text('PRAGMA foreign_keys=ON'))
        with self.Session() as db:
            erase_account(db,db.get(Customer,self.user['user']['id']));db.commit()
            self.assertIsNone(db.get(Customer,self.user['user']['id']))
            self.assertEqual(db.query(AdminMessage).count(),1)
            self.assertEqual(db.get(AdminMessage,retained['id']).body,'Other private message')
            self.assertFalse(db.query(AdminMessageCommand).filter_by(recipient_id=self.user['user']['id']).count())
            erase_account(db,db.get(Customer,self.admin['user']['id']));db.commit()
            row=db.get(AdminMessage,retained['id']);db.refresh(row)
            self.assertIsNone(row.sender_id);self.assertTrue(row.body_erased)
            self.assertNotIn('Other private message',row.body);self.assertFalse(row.requires_ack)
            self.assertEqual(db.query(AdminMessage).count(),1)

    def test_read_batch_is_atomic_if_one_id_belongs_to_other_account(self):
        own=self.send();foreign=self.send(account=self.other)
        rejected=self.read([own['id'],foreign['id']]);self.assertEqual(rejected.status_code,403)
        with self.Session() as db:
            self.assertIsNone(db.get(AdminMessage,own['id']).read_at)
            self.assertIsNone(db.get(AdminMessage,foreign['id']).read_at)

    def test_reply_rate_limit_keeps_idempotent_retry_available(self):
        identity=str(uuid4());payload={'body':'First reply','client_id':identity}
        one=self.client.post(OWN,headers=self.uh,json=payload)
        self.assertEqual(one.status_code,200)
        for index in range(19):self.reply(body=f'Reply {index}')
        rejected=self.client.post(OWN,headers=self.uh,json={'body':'Excess reply','client_id':str(uuid4())})
        self.assertEqual(rejected.status_code,429)
        again=self.client.post(OWN,headers=self.uh,json=payload)
        self.assertEqual(again.status_code,200)
        self.assertEqual(again.json()['message']['id'],one.json()['message']['id'])
        with self.Session() as db:self.assertEqual(db.query(AdminMessage).count(),20)
