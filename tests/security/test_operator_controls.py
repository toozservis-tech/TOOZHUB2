"""Operator actions are truthful, non-destructive and retain authorization."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import text
from fastapi import HTTPException
import test_account_flows as fixtures
from src.server import admin_api, control_center_jobs as jobs
from src.modules.vehicle_hub.models import Customer


class OperatorControls(unittest.TestCase):
    setUp = fixtures.AccountFlows.setUp
    tearDown = fixtures.AccountFlows.tearDown
    register = fixtures.AccountFlows.register

    def test_checks_detect_orphan_without_changing_data(self):
        with self.Session() as db:
            db.execute(text('CREATE TABLE operator_parent (id INTEGER PRIMARY KEY)'))
            db.execute(text('CREATE TABLE operator_child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES operator_parent(id))'))
            db.execute(text('INSERT INTO operator_child VALUES (1, 999), (2, NULL)'))
            db.commit()
            result = admin_api.repair_database(email='admin@example.com', db=db)
            self.assertFalse(result['success'])
            self.assertEqual(result['issues'], [{'table':'operator_child','target':'operator_parent','missing':1}])
            self.assertEqual(db.execute(text('SELECT COUNT(*) FROM operator_child')).scalar(), 2)
            db.execute(text('INSERT INTO operator_parent VALUES (999)')); db.commit()
            self.assertTrue(admin_api.repair_database(email='admin@example.com', db=db)['success'])
            self.assertGreater(admin_api.reindex_database(email='admin@example.com', db=db)['table_count'], 2)

    def test_disabled_worker_cannot_report_resumed(self):
        with patch.dict('os.environ', {'ENABLE_LICENSE_SUBSCRIPTION_WORKER':'0'}), patch.object(admin_api,'set_job_paused') as save:
            with self.assertRaises(HTTPException) as caught:
                admin_api.resume_control_center_job(admin_api.JobStateRequest(job_name='license.subscription.cycle',reason='test'),None,'admin@example.com',None)
            self.assertEqual(caught.exception.status_code,409);save.assert_not_called()

    def test_paused_run_never_processes_payments(self):
        with patch.object(admin_api,'is_job_paused',return_value=True), patch('src.modules.vehicle_hub.routers_v1.license_status.process_license_subscription_jobs') as process:
            with self.assertRaises(HTTPException) as caught:
                admin_api.run_control_center_job({'job_name':'license.subscription.cycle'},None,'admin@example.com',None)
            self.assertEqual(caught.exception.status_code,409);process.assert_not_called()

    def test_job_mutations_require_admin(self):
        account=self.register().json();headers={'Authorization':'Bearer '+account['access_token']}
        for role in ['user','service','admin','developer_admin']:
            with self.Session() as db:
                db.get(Customer,account['user']['id']).role=role;db.commit()
            for action in ['run','pause','resume']:
                with patch.object(admin_api,'set_job_paused') as save:
                    response=self.client.post('/admin-api/control-center/jobs/'+action,json={'job_name':'not-a-real-job','reason':'test'},headers=headers)
                    self.assertEqual(response.status_code,400 if role in {'admin','developer_admin'} else 403,(role,action,response.text));save.assert_not_called()

    def test_archived_account_is_hidden_from_counts_but_history_remains(self):
        from starlette.requests import Request
        admin = self.register('admin@example.com').json()['user']['id']
        target = self.register('service@example.com').json()['user']['id']
        with self.Session() as db:
            db.get(Customer,admin).role='developer_admin'
            db.get(Customer,target).role='service';db.commit()
            before=admin_api.get_overview('admin@example.com',db)
            result=admin_api.delete_admin_resource('services',target,admin_api.AdminDeleteRequest(reason='Synthetic test cleanup',confirmation='ODSTRANIT'),Request({'type':'http','headers':[],'client':('127.0.0.1',1)}),'admin@example.com',db)
            after=admin_api.get_overview('admin@example.com',db)
            self.assertTrue(result['soft_deleted'])
            self.assertEqual(after.total_users,before.total_users-1)
            self.assertEqual(after.total_services,0)
            self.assertEqual(db.query(Customer).count(),2)
            self.assertTrue(db.get(Customer,target).is_disabled)
            self.assertGreater(db.get(Customer,target).session_version,0)
            self.assertFalse(db.get(Customer,admin).is_deleted)

    def test_default_settings_preserve_existing_values(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(admin_api,'ADMIN_SETTINGS_FILE',Path(folder)/'settings.json'), patch.object(admin_api,'cached_file'), patch.object(admin_api,'persist_file',side_effect=lambda path,content,**kw:path.write_bytes(content)):
            admin_api.ADMIN_SETTINGS_FILE.write_text(json.dumps({'email':{'smtp_host':{'value':'existing.example.com','value_type':'string'}}}))
            result=admin_api.init_default_admin_settings('admin@example.com',None)
            self.assertEqual(result['settings']['email']['smtp_host']['value'],'existing.example.com')
            self.assertIn('security',result['settings'])

    def test_job_state_uses_durable_storage_and_corruption_stops_work(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(jobs,'JOBS_STATE_FILE',Path(folder)/'jobs.json'), patch.object(jobs,'cached_file') as refresh, patch.object(jobs,'persist_file',side_effect=lambda path,content,**kw:path.write_bytes(content)) as persist:
            jobs.set_job_paused('reminders.notification.check',True,'admin@example.com','maintenance')
            persist.assert_called_once();self.assertTrue(jobs.is_job_paused('reminders.notification.check'))
            refresh.assert_called_with(jobs.JOBS_STATE_FILE,refresh=True)
            jobs.set_job_paused('reminders.notification.check',False)
            self.assertFalse(jobs.is_job_paused('reminders.notification.check'))
            jobs.JOBS_STATE_FILE.write_text('{broken')
            with self.assertRaises(RuntimeError):jobs.is_job_paused('reminders.notification.check')

if __name__ == '__main__': unittest.main()
