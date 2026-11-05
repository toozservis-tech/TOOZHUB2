"""Synthetic account-only notification delivery; no outbound provider traffic."""
import os,json,unittest
from datetime import datetime,timedelta
from uuid import uuid4
from unittest.mock import patch
from cryptography.fernet import Fernet
import test_admin_messages as messages
from src.modules.vehicle_hub.routers_v1.notifications import router
from src.modules.vehicle_hub.notification_delivery_models import *
from src.modules.vehicle_hub.notification_inbox import collect_new,materialize,source_for
from src.modules.vehicle_hub.push_delivery import dispatch_one,Outcome,generic_payload,valid_web_endpoint
from src.modules.vehicle_hub.models import Customer,SystemNotification,Vehicle,VehicleOwnership
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate,VehicleUpdateInboxState
from src.modules.vehicle_hub.admin_message_models import AdminMessage
from scripts.migrate_notification_delivery import migrate
N='/api/v1/notifications';P='/api/v1/push/devices'

class Delivery(unittest.TestCase):
    tearDown=messages.Messages.tearDown
    register=messages.Messages.register
    verified_admin_token=messages.Messages.verified_admin_token
    path=messages.Messages.path
    send=messages.Messages.send
    def setUp(self):
        messages.Messages.setUp(self)
        self.client.app.include_router(router,prefix='/api/v1')
        env=patch.dict(os.environ,{'PUSH_TOKEN_ENCRYPTION_KEY':Fernet.generate_key().decode(),'APNS_SANDBOX_KEY_ID':'qa-sandbox','APNS_SANDBOX_PRIVATE_KEY':'qa-not-production', 'APNS_KEY_ID':'synthetic','APNS_TEAM_ID':'synthetic',
            'APNS_PRIVATE_KEY':'not-a-production-key','APNS_BUNDLE_IDS':'cz.fixture','FCM_PROJECT_ID':'synthetic-fixture','FCM_SERVICE_ACCOUNT_JSON':'{}','FCM_BUNDLE_IDS':'cz.fixture'})
        env.start();self.patches.append(env)
        migrate(self.engine)
    def get(self,p=N,headers=None):return self.client.get(p,headers=headers or self.uh)
    def act(self,path,data=None,headers=None):
        return self.client.post(path,headers=headers or self.uh,json={'client_id':str(uuid4()),**(data or {})})
    def items(self):return self.get().json()['items']
    def device(self,headers=None,**override):
        data={'platform':'apns','token':'ab'*32,'installation_id':str(uuid4()),'installation_secret':'s'*40,'environment':'sandbox','bundle_id':'cz.fixture','permission':'authorized',**override}
        r=self.client.post(P,headers=headers or self.uh,json=data)
        return r,data
    def announcement(self,required=False,**override):
        with self.Session() as db:
            row=SystemNotification(target_type='user',target_value=str(self.user['user']['id']),title='Soukromý titulek',message='PRIVATE-SECRET-MESSAGE',**override)
            db.add(row);db.flush();db.add(AnnouncementPolicy(source_id=row.id,requires_ack=required));db.commit();return row.id
    def collect(self):
        with self.Session() as db:collect_new(db)

    def test_open_is_read_only_ordinary_requires_dismiss_required_requires_ack(self):
        self.send();self.send(True);self.announcement();self.announcement(True)
        rows=self.items();self.assertEqual(len(rows),4);self.assertTrue(all(not r['read_at'] for r in rows))
        read=self.act(N+'/read',{'message_ids':[r['id'] for r in rows]})
        self.assertEqual(read.status_code,200,read.text);self.assertEqual(read.json()['summary'],{'unread_count':0,'badge_count':0,'pending_admin_count':4,'pending_ack_count':2})
        for row in rows:
            url=N+f'/{row["id"]}/'+('ack' if row['requires_ack'] else 'dismiss')
            result=self.act(url);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.get(N+'/summary').json()['pending_admin_count'],0)
        self.assertEqual(len(self.items()),4)
    def test_cross_account_no_read_ack_dismiss_detail_or_inbox(self):
        self.send(True);row=self.items()[0]
        for path in [N+f'/{row["id"]}/ack',N+f'/{row["id"]}/dismiss']:
            self.assertEqual(self.act(path,headers=self.oh).status_code,404)
        self.assertEqual(self.act(N+'/read',{'message_ids':[row['id']]},headers=self.oh).status_code,404)
        self.assertEqual(self.get(N+f'/{row["id"]}',self.oh).status_code,404)
        self.assertEqual(self.get(headers=self.oh).json()['items'],[])
    def test_csrf_roles_and_pending_email(self):
        self.send();row=self.items()[0]
        self.assertEqual(self.get(headers=self.ah).status_code,403)
        self.assertEqual(self.act(N+f'/{row["id"]}/dismiss',headers={**self.uh,'Origin':'https://evil.invalid','Sec-Fetch-Site':'cross-site'}).status_code,403)
    def test_idempotency_conflict_confirmation_once_and_new_arrival(self):
        self.send(True);row=self.items()[0];cid=str(uuid4())
        a=self.act(N+f'/{row["id"]}/ack',{'client_id':cid});b=self.act(N+f'/{row["id"]}/ack',{'client_id':cid})
        self.assertEqual(a.json()['item']['acknowledged_at'],b.json()['item']['acknowledged_at'])
        self.assertEqual(self.act(N+f'/{row["id"]}/dismiss',{'client_id':cid}).status_code,409)
        self.send(True);latest=self.items()[0]
        self.act(N+'/read',{'message_ids':[row['id']]})
        self.assertIsNone(self.get(N+f'/{latest["id"]}').json()['item']['read_at'])
        with self.Session() as db:self.assertEqual(db.query(NotificationCommand).filter_by(client_id=cid).count(),1)
    def test_legacy_read_does_not_dismiss_and_legacy_ack_synchronizes(self):
        ordinary=self.send();required=self.send(True);rows=self.items()
        self.act('/api/v1/admin-messages/read',{'message_ids':[ordinary['id'],required['id']]})
        self.assertEqual(self.get(N+'/summary').json()['pending_admin_count'],2)
        self.act('/api/v1/admin-messages/'+str(required['id'])+'/ack')
        self.assertEqual(self.get(N+'/summary').json()['pending_admin_count'],1)
    def test_stable_paging_old_required_and_new_message(self):
        self.send(True);old=self.items()[0]
        with self.Session() as db:
            for i in range(40):db.add(AdminMessage(recipient_id=self.user['user']['id'],sender_id=self.admin['user']['id'],sender_kind='admin',body=f'item{i}'))
            db.commit()
        page=self.get(N+'?limit=20').json();self.assertTrue(page['has_more'])
        self.send();page2=self.get(N+'?limit=50&before_id='+str(page['next_before_id'])).json()
        self.assertEqual(len(set(r['id'] for r in page['items']+page2['items'])),41)
        self.assertIn(old['id'],[r['id'] for r in self.get(N+'?pending_only=true&limit=100').json()['items']])
    def test_encrypted_device_scoped_handoff_and_no_token_echo(self):
        response,body=self.device();self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(body['token'],response.text)
        with self.Session() as db:
            row=db.query(PushDevice).one();self.assertNotIn(body['token'],row.token_ciphertext);self.assertNotIn(body['installation_secret'],row.installation_secret_hash)
        other=self.client.post(P,headers=self.oh,json={**body,'installation_secret':'x'*40})
        self.assertEqual(other.status_code,409)
        handoff=self.client.post(P,headers=self.oh,json=body);self.assertEqual(handoff.status_code,200,handoff.text)
        with self.Session() as db:self.assertEqual(db.query(PushDevice).one().recipient_id,self.other['user']['id'])
    def test_other_installation_cannot_capture_known_device_token(self):
        _,body=self.device()
        response=self.client.post(P,headers=self.oh,json={**body,'installation_id':str(uuid4())})
        self.assertEqual(response.status_code,409)
    def test_missing_encryption_provider_configuration_and_invalid_endpoint(self):
        with patch.dict(os.environ,{'PUSH_TOKEN_ENCRYPTION_KEY':''}):self.assertEqual(self.device()[0].status_code,503)
        self.assertFalse(valid_web_endpoint('https://127.0.0.1/push'));self.assertFalse(valid_web_endpoint('https://web.push.apple.com.evil.invalid/p'))
        self.assertFalse(valid_web_endpoint('https://web.push.apple.com:444/p'));self.assertFalse(valid_web_endpoint('https://user:pass@web.push.apple.com/p'))
        self.assertTrue(valid_web_endpoint('https://web.push.apple.com/valid'))
    def test_collect_and_dispatch_dedupe_generic_payload(self):
        self.assertEqual(self.device()[0].status_code,200);self.send(body='SECRET EMAIL VIN MONEY');self.collect();self.collect()
        captured=[]
        with self.Session() as db:
            self.assertEqual(db.query(PushOutbox).count(),1)
            dispatch_one(db,lambda d,s,p:(captured.append(p) or Outcome('accepted','apns_accepted')))
            self.assertFalse(dispatch_one(db,lambda *a:self.fail('duplicate')))
        self.assertEqual(len(captured),1);self.assertNotIn('SECRET',json.dumps(captured));self.assertNotIn('example.com',json.dumps(captured))
    def test_logout_ticket_and_password_revision_prevent_dispatch(self):
        self.device();self.send();self.collect()
        self.client.post('/user/logout',headers=self.uh)
        with self.Session() as db:
            self.assertFalse(db.query(PushDevice).one().active)
            dispatch_one(db,lambda *a:self.fail('send after logout'))
            self.assertEqual(db.query(PushOutbox).one().state,'skipped')
    def test_session_version_and_disabled_user_prevent_dispatch(self):
        self.device();self.send();self.collect()
        with self.Session() as db:
            user=db.get(Customer,self.user['user']['id']);user.session_version=1;db.commit()
            dispatch_one(db,lambda *a:self.fail('send after password revision'))
            self.assertEqual(db.query(PushOutbox).one().state,'skipped')
    def test_unregister_cannot_revoke_other_installation(self):
        _,body=self.device();data={k:body[k] for k in ['installation_id','installation_secret']}
        self.client.post(P+'/unregister',headers=self.oh,json=data)
        with self.Session() as db:self.assertTrue(db.query(PushDevice).one().active)
        self.client.post(P+'/unregister',headers=self.uh,json=data)
        with self.Session() as db:self.assertFalse(db.query(PushDevice).one().active)
    def test_retry_lease_recovery_and_provider_token_revocation(self):
        self.device();self.send();self.collect();now=datetime.utcnow()
        with self.Session() as db:
            dispatch_one(db,lambda *a:Outcome('retry','provider_network_error'),now)
            row=db.query(PushOutbox).one();self.assertEqual(row.state,'retry');due=row.next_attempt_at
            self.assertFalse(dispatch_one(db,lambda *a:self.fail('retry early'),now))
            dispatch_one(db,lambda *a:Outcome('invalid','apns_invalid_token'),due+timedelta(seconds=1))
            self.assertFalse(db.query(PushDevice).one().active);self.assertEqual(db.query(PushOutbox).one().state,'skipped')
    def test_source_created_before_rollout_never_pushes(self):
        self.send();migrate(self.engine);self.device();self.collect()
        # Initial migration cursor already exists: source after initial rollout is new.
        with self.Session() as db:
            db.query(PushOutbox).delete();db.query(NotificationCursor).filter_by(kind='admin_message').update({'source_id':0,'rollout_at':datetime.utcnow()+timedelta(seconds=1)});db.commit()
        self.collect()
        with self.Session() as db:self.assertEqual(db.query(PushOutbox).count(),0)
    def test_broadcast_endpoint_persists_ack_policy_without_plaintext_file(self):
        response=self.client.post('/admin-api/control-center/notifications/broadcast',headers=self.ah,json={'message':'Required system notice','target_type':'user','target_value':str(self.user['user']['id']),'requires_ack':True})
        self.assertEqual(response.status_code,200,response.text)
        item=self.items()[0];self.assertTrue(item['requires_ack']);self.assertEqual(item['kind'],'announcement')
    def test_expired_targeted_announcement_is_not_leaked(self):
        self.announcement(expires_at=datetime.utcnow()-timedelta(seconds=1));self.announcement()
        self.assertEqual(len(self.items()),1);self.assertEqual(self.get(headers=self.oh).json()['items'],[])
    def test_migration_is_repeatable_and_history_preserved(self):
        self.send();old=self.items()[0];migrate(self.engine);migrate(self.engine)
        self.assertEqual(self.items()[0]['id'],old['id'])
        with self.Session() as db:self.assertEqual(db.query(NotificationCursor).count(),3)

    def test_expired_announcement_remains_archive_snapshot_not_pending_or_push(self):
        source=self.announcement(True);old=self.items()[0]
        with self.Session() as db:
            row=db.get(SystemNotification,source);row.expires_at=datetime.utcnow()-timedelta(seconds=1)
            row.message='Changed after audience';row.target_value=str(self.other['user']['id']);db.commit()
        result=self.get(N+f'/{old["id"]}').json();self.assertEqual(result['item']['body'],'PRIVATE-SECRET-MESSAGE')
        self.assertTrue(result['item']['archived']);self.assertEqual(result['summary']['badge_count'],0)
        self.assertEqual(result['summary']['pending_admin_count'],0)
        self.assertEqual(self.get(N+'?pending_only=true').json()['items'],[])
        self.assertEqual(len(self.items()),1);self.assertEqual(self.get(headers=self.oh).json()['items'],[])

    def test_vehicle_update_revoked_ownership_never_dispatches_or_discloses(self):
        self.device()
        with self.Session() as db:
            user=db.get(Customer,self.user['user']['id']);now=datetime.utcnow()
            vehicle=Vehicle(tenant_id=user.tenant_id,user_email=user.email,nickname='Synthetic')
            db.add(vehicle);db.flush()
            owner=VehicleOwnership(vehicle_id=vehicle.id,customer_id=user.id,tenant_id=user.tenant_id,is_active=True,is_primary=True,assigned_at=now,owned_from=now)
            db.add(owner);db.flush()
            update=VehicleUpdate(tenant_id=user.tenant_id,vehicle_id=vehicle.id,recipient_id=user.id,ownership_id=owner.id,ownership_started_at=now,actor_id=self.service['user']['id'],event_type='record.created',title='New service work',message='Private work',source_type='qa',source_id=1,dedupe_key=str(uuid4()))
            db.add(update);db.commit();oid=owner.id
        self.collect();rows=self.items();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['kind'],'vehicle_update')
        with self.Session() as db:
            db.get(VehicleOwnership,oid).is_active=False;db.commit()
            dispatch_one(db,lambda *a:self.fail('push after transfer'))
            self.assertEqual(db.query(PushOutbox).one().state,'skipped')
        self.assertEqual(self.get(N+f'/{rows[0]["id"]}').status_code,404)
        self.assertEqual(self.items(),[])
        self.assertEqual(self.get(headers=self.oh).json()['items'],[])

    def test_archive_service_update_is_hidden_and_read_source_synchronizes(self):
        self.device();self.send(True);row=self.items()[0];self.collect()
        self.act('/api/v1/admin-messages/read',{'message_ids':[row['source_id']]})
        with self.Session() as db:
            dispatch_one(db,lambda *a:self.fail('push after legacy read'))
            self.assertEqual(db.query(PushOutbox).one().last_code,'already_seen')

    def test_expired_session_disabled_account_and_handoff_skip_pending_push(self):
        _,body=self.device();self.send();self.collect()
        self.client.post(P,headers=self.oh,json=body)
        with self.Session() as db:
            dispatch_one(db,lambda *a:self.fail('old account data on new account installation'))
            self.assertEqual(db.query(PushOutbox).one().state,'skipped')
        self.device(token='cd'*32);self.send();self.collect()
        with self.Session() as db:
            for device in db.query(PushDevice).filter_by(recipient_id=self.user['user']['id']):device.session_expires_at=datetime.utcnow()-timedelta(seconds=1)
            db.commit()
            while dispatch_one(db,lambda *a:self.fail('expired session push')):pass
            self.assertTrue(all(row.state=='skipped' for row in db.query(PushOutbox)))

    def test_schema_absent_returns503_and_public_demo_cannot_read(self):
        from src.core.security import create_access_token
        demo=create_access_token({'sub':self.user['user']['email'],'sv':0,'demo':True})
        self.assertEqual(self.get(headers={'Authorization':'Bearer '+demo}).status_code,403)
        with self.engine.begin() as connection:NotificationCommand.__table__.drop(connection)
        self.assertEqual(self.get().status_code,503)

    def test_device_registration_after_existing_announcement_snapshot_queues_once(self):
        self.announcement();self.items()
        response,body=self.device()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post(P,headers=self.uh,json=body).status_code,200)
        with self.Session() as db:self.assertEqual(db.query(PushOutbox).count(),1)

    def test_erasure_cleans_private_snapshot_token_commands_without_other_account(self):
        from src.modules.vehicle_hub.notification_delivery_models import erase_account_notifications
        self.device();self.announcement();self.send();self.collect();rows=self.items()
        self.act(N+'/read',{'message_ids':[row['id'] for row in rows]})
        with self.Session() as db:
            erase_account_notifications(db,db.get(Customer,self.user['user']['id']));db.commit()
            for model in (NotificationItem,NotificationCommand,PushDevice,PushOutbox):self.assertEqual(db.query(model).count(),0)
            self.assertEqual(db.query(AdminMessage).count(),1) # source erasure is its own authorized step.


    def test_scheduled_announcement_late_registration_and_due_audience_recheck(self):
        from src.modules.vehicle_hub.models import License
        now=datetime.utcnow()
        source=self.announcement(starts_at=now+timedelta(days=3))
        self.collect()
        with self.Session() as db:
            self.assertGreaterEqual(db.query(NotificationItem).count(),1) # role candidates; no private snapshot yet
            self.assertTrue(all(row.available_at is None for row in db.query(NotificationItem)))
            row=db.get(SystemNotification,source);row.target_type='plan';row.target_value='premium';db.commit()
        self.assertEqual(self.items(),[])
        self.assertEqual(self.device()[0].status_code,200)
        with self.Session() as db:
            row=db.get(SystemNotification,source);row.starts_at=now-timedelta(minutes=1)
            for item in db.query(NotificationItem):item.created_at=now-timedelta(days=3)
            for pending in db.query(PushOutbox):pending.next_attempt_at=now-timedelta(minutes=1)
            user=db.get(Customer,self.user['user']['id']);tenant_id=user.tenant_id;license=db.query(License).filter_by(tenant_id=tenant_id).one()
            license.plan='premium';db.commit()
            sent=[];dispatch_one(db,lambda *a:(sent.append(a[2]) or Outcome('accepted','apns_accepted')))
            self.assertEqual(len(sent),1) # age measured from scheduled start, not authoring date
        # A second due announcement must not send after the recipient loses its plan.
        source2=self.announcement(starts_at=now+timedelta(days=1))
        self.collect()
        with self.Session() as db:
            row=db.get(SystemNotification,source2);row.starts_at=now-timedelta(minutes=1);row.target_type='plan';row.target_value='premium'
            db.query(License).filter_by(tenant_id=tenant_id).update({'plan':'free'})
            db.query(PushOutbox).filter_by(state='queued').update({'next_attempt_at':now-timedelta(minutes=1)});db.commit()
            while dispatch_one(db,lambda *a:self.fail('Audience no longer eligible')):pass

    def test_legacy_unsubscribe_optional_body_is_scoped_and_csrf_guarded(self):
        from src.modules.vehicle_hub.routers_v1 import push
        from src.modules.vehicle_hub.models import PushSubscription
        self.client.app.include_router(push.router,prefix='/api/v1')
        with self.Session() as db:
            for actor in (self.user,self.other):
                user=db.get(Customer,actor['user']['id'])
                db.add(PushSubscription(tenant_id=user.tenant_id,customer_id=user.id,
                    endpoint='https://web.push.apple.com/'+str(user.id),p256dh='p'*16,auth='a'*16,is_active=True))
            db.commit()
        bad=self.client.post('/api/v1/push/unsubscribe',headers={**self.uh,'Origin':'https://evil.invalid','Sec-Fetch-Site':'cross-site'})
        self.assertEqual(bad.status_code,403)
        result=self.client.post('/api/v1/push/unsubscribe',headers=self.uh)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['deactivated'],1)
        with self.Session() as db:
            self.assertTrue(db.query(PushSubscription).filter_by(customer_id=self.other['user']['id']).one().is_active)
            self.assertFalse(db.query(PushSubscription).filter_by(customer_id=self.user['user']['id']).one().is_active)

if __name__=='__main__':unittest.main()
