"""Synthetic reverse delivery: exact original author, no implicit broadcast."""
import json,unittest
from uuid import uuid4
from unittest.mock import patch
from datetime import datetime,timedelta
import test_notification_delivery as delivery
from src.modules.vehicle_hub.models import Customer,SystemNotification
from src.modules.vehicle_hub.admin_message_models import AdminMessage
from src.modules.vehicle_hub.notification_delivery_models import NotificationItem,PushOutbox,AnnouncementPolicy
from src.modules.vehicle_hub.notification_inbox import collect_new,materialize
from src.modules.vehicle_hub.push_delivery import dispatch_one,Outcome
from src.core.security import create_access_token
from scripts.migrate_reverse_notifications import migrate

N='/api/v1/notifications';M='/api/v1/admin-messages'
class ReverseDelivery(unittest.TestCase):
    tearDown=delivery.Delivery.tearDown
    register=delivery.Delivery.register
    verified_admin_token=delivery.Delivery.verified_admin_token
    path=delivery.Delivery.path
    send=delivery.Delivery.send
    device=delivery.Delivery.device
    act=delivery.Delivery.act
    get=delivery.Delivery.get
    collect=delivery.Delivery.collect
    def setUp(self):
        delivery.Delivery.setUp(self);migrate(self.engine)
        self.admin2=self.register('another-admin@example.com').json()
        with self.Session() as db:
            db.get(Customer,self.admin2['user']['id']).role='admin';db.commit()
        self.a2h={'Authorization':'Bearer '+self.verified_admin_token(self.admin2['user']['id'])}
    def reply(self,reference=None,headers=None,**fields):
        return self.act(M,{'body':'Synthetic recipient response',**(reference or {}),**fields},headers=headers)
    def admin_items(self,headers=None):return self.get(N,headers or self.ah).json()['items']

    def test_unreferenced_legacy_reply_has_no_target_and_no_admin_push(self):
        self.send();self.assertEqual(self.reply().status_code,200)
        self.collect();self.assertEqual(self.admin_items(),[]);self.assertEqual(self.admin_items(self.a2h),[])
        with self.Session() as db:
            row=db.query(AdminMessage).filter_by(sender_kind='recipient').one()
            self.assertIsNone(row.addressed_admin_id);self.assertIsNone(row.reply_to_message_id)
    def test_exact_reference_delivers_only_original_admin_and_read_is_independent(self):
        sent=self.send()
        newer=self.act(self.path(),{'body':'Another administrator spoke later','requires_ack':False},self.a2h)
        self.assertEqual(newer.status_code,200,newer.text)
        response=self.reply({'reply_to_message_id':sent['id']});self.assertEqual(response.status_code,200,response.text)
        reply_id=response.json()['message']['id'];rows=self.admin_items();self.assertEqual(len(rows),1)
        item=rows[0];self.assertEqual(item['kind'],'admin_reply');self.assertEqual(item['action']['type'],'admin_conversation')
        self.assertEqual(item['action']['id'],self.user['user']['id']);self.assertEqual(self.admin_items(self.a2h),[])
        # The collective support inbox remains available to another authorized admin,
        # but their read must not clear the addressed author's individual unread badge.
        r=self.act(self.path()+'/read',{'message_ids':[reply_id]},self.a2h);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.get(N+'/summary',self.ah).json()['badge_count'],1)
        self.assertEqual(self.get(N+f'/{item["id"]}',self.a2h).status_code,404)
        r=self.act(N+'/read',{'message_ids':[item['id']]},self.ah);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['summary']['badge_count'],0)
        self.assertEqual(self.act(N+f'/{item["id"]}/ack',headers=self.ah).status_code,409)
    def test_targeted_author_legacy_read_prevents_late_unread_materialization(self):
        sent=self.send();reply=self.reply({'reply_to_message_id':sent['id']}).json()['message']
        result=self.act(self.path()+'/read',{'message_ids':[reply['id']]},self.ah)
        self.assertEqual(result.status_code,200,result.text);self.assertTrue(self.admin_items()[0]['read_at'])
        self.assertEqual(self.get(N+'/summary',self.ah).json()['unread_count'],0)
    def test_foreign_reference_recipient_reply_and_spoofed_target_rejected(self):
        sent=self.send();mine=self.reply().json()['message']
        for ref,headers in [({'reply_to_message_id':sent['id']},self.oh),({'reply_to_message_id':mine['id']},self.uh),({'reply_to_message_id':99999},self.uh)]:
            self.assertEqual(self.reply(ref,headers).status_code,404)
        self.assertEqual(self.reply({'reply_to_message_id':sent['id'],'addressed_admin_id':self.admin2['user']['id']}).status_code,422)
        self.assertEqual(self.reply({'reply_to_message_id':sent['id'],'reply_to_notification_id':1}).status_code,422)
        self.assertEqual(self.admin_items(),[])
    def test_uuid_retry_deduplicates_and_reference_is_part_of_command_identity(self):
        a=self.send();b=self.send();cid=str(uuid4());ref={'reply_to_message_id':a['id'],'client_id':cid}
        first=self.reply(ref);again=self.reply(ref)
        self.assertEqual(first.json()['message']['id'],again.json()['message']['id'])
        self.assertEqual(self.reply({'reply_to_message_id':b['id'],'client_id':cid}).status_code,409)
        self.collect();self.collect();self.assertEqual(len(self.admin_items()),1)
    def test_admin_assurance_cross_site_and_demo_block_notification_details(self):
        sent=self.send();self.reply({'reply_to_message_id':sent['id']});item=self.admin_items()[0]
        unverified={'Authorization':'Bearer '+self.admin['access_token']}
        r=self.get(N,unverified);self.assertEqual(r.status_code,403);self.assertEqual(r.headers.get('x-admin-verification'),'required')
        self.assertEqual(self.get(N+f'/{item["id"]}',unverified).status_code,403)
        self.assertEqual(self.act(N+'/read',{'message_ids':[item['id']]},unverified).status_code,403)
        self.assertEqual(self.act(N+'/read',{'message_ids':[item['id']]},{**self.ah,'Origin':'https://evil.invalid'}).status_code,403)
    def test_role_revocation_before_collect_and_before_send_cancels_delivery(self):
        self.assertEqual(self.device(headers=self.ah)[0].status_code,200)
        sent=self.send();self.reply({'reply_to_message_id':sent['id']});self.collect()
        with self.Session() as db:
            db.get(Customer,self.admin['user']['id']).role='user';db.commit()
            dispatch_one(db,lambda *a:self.fail('Role-revoked administrator must not receive push'))
            self.assertEqual(db.query(PushOutbox).one().state,'skipped')
        self.assertEqual(self.admin_items(),[])
    def test_author_disabled_at_reply_time_leaves_legacy_inbox_without_reassignment(self):
        sent=self.send()
        with self.Session() as db:db.get(Customer,self.admin['user']['id']).is_disabled=True;db.commit()
        result=self.reply({'reply_to_message_id':sent['id']});self.assertEqual(result.status_code,200,result.text)
        with self.Session() as db:self.assertIsNone(db.get(AdminMessage,result.json()['message']['id']).addressed_admin_id)
        self.assertEqual(result.json()['message']['reply_delivery'],'unavailable')
        self.assertEqual(self.admin_items(self.a2h),[])
    def test_announcement_reply_requires_visible_target_and_original_author(self):
        with self.Session() as db:
            row=SystemNotification(target_type='user',target_value=str(self.user['user']['id']),title='Notice',message='Synthetic',created_by_customer_id=self.admin['user']['id'])
            db.add(row);db.commit();identity=row.id
        self.assertEqual(self.reply({'reply_to_notification_id':identity},self.oh).status_code,404)
        self.assertEqual(self.reply({'reply_to_notification_id':identity}).status_code,200)
        self.assertEqual(len(self.admin_items()),1)
        # Materialized eligible archive retains its reference; never-visible scheduled notices do not.
        self.get(N)
        with self.Session() as db:
            db.get(SystemNotification,identity).is_active=False
            hidden=SystemNotification(target_type='all',starts_at=datetime.utcnow()+timedelta(days=1),title='Future',message='Hidden',created_by_customer_id=self.admin['user']['id'])
            db.add(hidden);db.commit();future_id=hidden.id
        self.collect()
        self.assertEqual(self.reply({'reply_to_notification_id':future_id}).status_code,404)
        self.assertEqual(self.reply({'reply_to_notification_id':identity}).status_code,200)
    def test_service_recipient_explicit_reply_and_provider_payload_never_private(self):
        self.assertEqual(self.device(headers=self.ah)[0].status_code,200)
        self.assertEqual(self.device(headers=self.a2h,token='cd'*32)[0].status_code,200)
        sent=self.send(account=self.service);r=self.reply({'reply_to_message_id':sent['id']},self.sh,body='PRIVATE-123 email@example.com VIN')
        self.assertEqual(r.status_code,200,r.text);self.collect();self.collect();seen=[]
        with self.Session() as db:
            self.assertEqual(db.query(PushOutbox).count(),1)
            dispatch_one(db,lambda d,s,p:(seen.append((d.recipient_id,p)) or Outcome('accepted','apns_accepted')))
        self.assertEqual(seen[0][0],self.admin['user']['id']);self.assertNotIn('PRIVATE',json.dumps(seen));self.assertNotIn('example.com',json.dumps(seen))
    def test_read_and_role_change_do_not_reinterpret_reference_as_broadcast(self):
        sent=self.send();self.reply({'reply_to_message_id':sent['id']});item=self.admin_items()[0]
        self.act(N+'/read',{'message_ids':[item['id']]},self.ah)
        self.assertEqual(self.device(headers=self.ah)[0].status_code,200);self.collect()
        with self.Session() as db:self.assertEqual(db.query(PushOutbox).count(),0)
    def test_migration_baseline_prevents_historical_reply_push_even_after_opt_in(self):
        from src.modules.vehicle_hub.notification_delivery_models import NotificationCursor
        sent=self.send();self.reply({'reply_to_message_id':sent['id']})
        with self.Session() as db:db.query(NotificationCursor).filter(NotificationCursor.kind.in_(['admin_reply','service_event'])).delete(synchronize_session=False);db.commit()
        migrate(self.engine)
        self.assertEqual(len(self.admin_items()),1)
        self.assertEqual(self.device(headers=self.ah)[0].status_code,200);self.collect()
        with self.Session() as db:self.assertEqual(db.query(PushOutbox).count(),0)
        self.reply({'reply_to_message_id':sent['id']});self.collect()
        with self.Session() as db:self.assertEqual(db.query(PushOutbox).count(),1)
    def test_erasure_preserves_foreign_conversation_and_removes_addressed_private_content(self):
        from src.modules.vehicle_hub.account_erasure import erase_account
        from sqlalchemy import text
        original=self.send();self.reply({'reply_to_message_id':original['id']});self.admin_items()
        retained=self.send(account=self.other)
        with self.engine.connect() as conn:conn.execute(text('PRAGMA foreign_keys=ON'))
        with self.Session() as db:
            erase_account(db,db.get(Customer,self.user['user']['id']));db.commit()
            self.assertEqual(db.query(AdminMessage).one().id,retained['id'])
            self.assertFalse(db.execute(text('PRAGMA foreign_key_check')).all())
        self.assertEqual(self.admin_items(),[])
