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
    verified_admin_token = fixtures.AccountFlows.verified_admin_token

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

    def test_disabled_workers_can_be_enabled_durably_and_paused(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(jobs, 'JOBS_STATE_FILE', Path(folder)/'jobs.json'), patch.object(jobs, 'cached_file'), patch.object(jobs, 'persist_file', side_effect=lambda path,content,**kw:path.write_bytes(content)), patch.object(admin_api, 'log_developer_action'), patch('src.modules.licensing.apple_reconciliation.require_ready'):
            for name, env in jobs.JOB_ENABLE_ENV.items():
                with self.subTest(job=name), patch.dict('os.environ', {env:'0'}):
                    self.assertFalse(jobs.should_run_job(name))
                    result = admin_api.resume_control_center_job(admin_api.JobStateRequest(job_name=name,reason='Enable synthetic test'),None,'admin@example.com',None)
                    self.assertTrue(result['enabled'])
                    # Re-read the persisted file, as after a process restart.
                    self.assertTrue(jobs.should_run_job(name))
                    self.assertEqual(jobs.load_jobs_state()['last_change'][name]['actor'], 'admin@example.com')
                    admin_api.pause_control_center_job(admin_api.JobStateRequest(job_name=name,reason='Pause synthetic test'),None,'admin@example.com',None)
                    self.assertFalse(jobs.should_run_job(name))
                    self.assertTrue(jobs.is_job_enabled(name))
                    admin_api.resume_control_center_job(admin_api.JobStateRequest(job_name=name,reason='Resume synthetic test'),None,'admin@example.com',None)
                    self.assertTrue(jobs.should_run_job(name))
            for value in [{'enabled': []}, {'enabled': {'license.subscription.cycle': 'false'}}, {'last_change': []}]:
                jobs.JOBS_STATE_FILE.write_text(json.dumps(value))
                with self.assertRaises(RuntimeError): jobs.should_run_job('license.subscription.cycle')

    def test_running_worker_observes_enable_and_disable_without_restart(self):
        # Execute the actual worker body without importing startup/server side effects.
        import ast
        import asyncio
        from unittest.mock import MagicMock
        from types import SimpleNamespace
        source = ast.parse(Path('src/server/bootstrap.py').read_text())
        cases = [
            ('_reminder_notification_worker', 'src.modules.vehicle_hub.routers_v1.reminders.check_and_send_reminder_notifications', 'REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC'),
            ('_license_subscription_worker', 'src.modules.vehicle_hub.routers_v1.license_status.process_license_subscription_jobs', 'LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC'),
        ]
        for worker_name, processor, interval_key in cases:
            with self.subTest(worker=worker_name):
                sleeps = []
                async def sleep(seconds):
                    sleeps.append(seconds)
                    if len(sleeps) == 4:
                        raise asyncio.CancelledError()
                gate = MagicMock(side_effect=[False, True, False])
                session = MagicMock()
                scope = {'asyncio': SimpleNamespace(sleep=sleep), 'SessionLocal': lambda: session,
                         'should_run_job': gate, interval_key: 300}
                definition = next(node for node in source.body if isinstance(node, ast.AsyncFunctionDef) and node.name == worker_name)
                exec(compile(ast.Module(body=[definition], type_ignores=[]), '<actual-worker>', 'exec'), scope)
                with patch(processor, return_value={}) as process:
                    with self.assertRaises(asyncio.CancelledError): asyncio.run(scope[worker_name]())
                    process.assert_called_once_with(db=session)
                self.assertEqual(gate.call_count, 3)
                self.assertEqual(session.close.call_count, 3)

    def test_confirmed_file_erasure_cannot_be_paused_or_falsely_resumed(self):
        with patch.object(admin_api,'set_job_paused') as save:
            for action in [admin_api.pause_control_center_job,admin_api.resume_control_center_job]:
                with self.assertRaises(HTTPException) as caught:
                    action(admin_api.JobStateRequest(job_name='privacy.files.erase',reason='fixture'),None,'admin@example.com',None)
                self.assertEqual(caught.exception.status_code,409)
            save.assert_not_called()

    def test_manual_file_cleanup_uses_one_bounded_existing_request(self):
        with patch.object(admin_api,'is_job_paused',return_value=False), patch.object(admin_api,'log_developer_action'), patch('src.core.file_erasure.process_file_erasures',return_value={'removed':0,'retrying':1}) as cleanup:
            result=admin_api.run_control_center_job({'job_name':'privacy.files.erase'},None,'admin@example.com',None)
            cleanup.assert_called_once_with(limit=1)
            self.assertEqual(result['result']['retrying'],1)

    def test_paused_run_never_processes_payments(self):
        with patch.object(admin_api,'is_job_paused',return_value=True), patch('src.modules.vehicle_hub.routers_v1.license_status.process_license_subscription_jobs') as process:
            with self.assertRaises(HTTPException) as caught:
                admin_api.run_control_center_job({'job_name':'license.subscription.cycle'},None,'admin@example.com',None)
            self.assertEqual(caught.exception.status_code,409);process.assert_not_called()

    def test_job_mutations_require_admin(self):
        account=self.register().json();headers={'Authorization':'Bearer '+self.verified_admin_token(account['user']['id'])}
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
