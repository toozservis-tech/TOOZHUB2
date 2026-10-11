"""Real HTTP/DB round trips on isolated data; never live payments or delivery."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_account_flows as fixtures
from src.server import admin_api, control_center_jobs as jobs
from src.modules.vehicle_hub.models import Customer


class AdminOperationsRoundtrip(unittest.TestCase):
    register = fixtures.AccountFlows.register
    verified_admin_token = fixtures.AccountFlows.verified_admin_token

    def setUp(self):
        fixtures.AccountFlows.setUp(self)
        # Retain the actual audit writer, not the general account fixture mock.
        self.patches[6].stop()
        self.files = tempfile.TemporaryDirectory(dir=jobs.DATA_DIR)
        self.addCleanup(self.files.cleanup)
        for attr, name in [('CONTROL_CENTER_BACKUP_DIR','backups'), ('CONTROL_CENTER_LOG_DIR','logs')]:
            path = Path(self.files.name)/name
            path.mkdir()
            p = patch.object(admin_api, attr, path)
            p.start()
            self.addCleanup(p.stop)
        account = self.register('operator-roundtrip@example.com').json()['user']
        self.admin_id = account['id']
        with self.Session() as db:
            db.get(Customer, self.admin_id).role = 'developer_admin'
            db.commit()
        self.headers = {'Authorization': 'Bearer ' + self.verified_admin_token(self.admin_id)}

    tearDown = fixtures.AccountFlows.tearDown

    def test_account_controls_revoke_real_sessions_and_record_audit(self):
        account = self.register('roundtrip-customer@example.com').json()
        user_id = account['user']['id']
        old_headers = {'Authorization': 'Bearer '+account['access_token']}
        self.assertEqual(self.client.get('/test/protected', headers=old_headers).status_code, 200)
        def action(name, **extra):
            return self.client.post('/admin-api/control-center/users/'+str(user_id)+'/'+name,
                                    headers=self.headers, json={'reason': 'Isolated account verification', **extra})
        self.assertEqual(action('disable').status_code, 200)
        self.assertIn(self.client.get('/test/protected', headers=old_headers).status_code, [401,403])
        self.assertEqual(action('enable').status_code, 200)
        self.assertEqual(self.client.get('/test/protected', headers=old_headers).status_code, 401)
        login = self.client.post('/user/login', json={'email': 'roundtrip-customer@example.com', 'password': fixtures.PASSWORD})
        self.assertEqual(login.status_code, 200, login.text)
        active_headers = {'Authorization':'Bearer '+login.json()['access_token']}
        self.assertEqual(self.client.get('/test/protected', headers=active_headers).status_code, 200)
        self.assertEqual(action('force-logout').status_code, 200)
        self.assertEqual(self.client.get('/test/protected', headers=active_headers).status_code, 401)
        changed = action('reset-password', generate_random=False, new_password='Isolated-replacement-Password-985!')
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.post('/user/login', json={'email':'roundtrip-customer@example.com','password':fixtures.PASSWORD}).status_code, 401)
        self.assertEqual(self.client.post('/user/login', json={'email':'roundtrip-customer@example.com','password':'Isolated-replacement-Password-985!'}).status_code, 200)
        license_result = action('license', plan='basic', status='active')
        self.assertEqual(license_result.status_code, 200, license_result.text)
        self.assertEqual(license_result.json()['license']['vehicles_limit'], 5)
        audit = self.client.get('/admin-api/control-center/audit-actions', headers=self.headers).json()['items']
        self.assertTrue({'user.disable','user.enable','user.force_logout','user.password_reset','license.override'}.issubset({row['action_type'] for row in audit}))
        self.assertNotIn('Isolated-replacement-Password', json.dumps(audit))

    def test_notification_is_persisted_and_visible_with_audit(self):
        response = self.client.post('/admin-api/control-center/notifications/broadcast', headers=self.headers,
                                    json={'message':'Isolated verification notice', 'title':'Roundtrip', 'target_type':'all', 'severity':'info'})
        self.assertEqual(response.status_code, 200, response.text)
        notices = self.client.get('/admin-api/control-center/notifications', headers=self.headers)
        self.assertEqual(notices.status_code, 200, notices.text)
        self.assertEqual(notices.json()['items'][0]['id'], response.json()['notification_id'])
        audit = self.client.get('/admin-api/control-center/audit-actions', headers=self.headers).json()['items']
        self.assertEqual(audit[0]['action_type'], 'notifications.broadcast')

    def test_local_backup_download_and_restore_preserve_pre_restore_copy(self):
        import sqlite3
        import zipfile
        import io
        path = Path(self.files.name)/'synthetic.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE example (value TEXT)')
            db.execute("INSERT INTO example VALUES ('before')")
        with patch.object(admin_api, 'get_db_file_path', return_value=path):
            created = self.client.post('/admin-api/control-center/backups/create', headers=self.headers, json={'include_data_dir':False})
            self.assertEqual(created.status_code, 200, created.text)
            backup_id = created.json()['backup']['backup_id']
            archive = self.client.get('/admin-api/control-center/backups/'+backup_id+'/download', headers=self.headers)
            self.assertEqual(archive.status_code, 200, archive.text if archive.status_code != 200 else '')
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(archive.content)))
            with sqlite3.connect(path) as db:
                db.execute("UPDATE example SET value='after'")
            payload = {'backup_id':backup_id,'scope':'full','confirm_text':'wrong'}
            self.assertEqual(self.client.post('/admin-api/control-center/backups/restore', headers=self.headers, json=payload).status_code, 400)
            payload['confirm_text'] = admin_api.CONTROL_CENTER_DANGEROUS_CONFIRM
            restored = self.client.post('/admin-api/control-center/backups/restore', headers=self.headers, json=payload)
            self.assertEqual(restored.status_code, 200, restored.text)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT value FROM example').fetchone()[0], 'before')
            with sqlite3.connect(admin_api.CONTROL_CENTER_BACKUP_DIR/restored.json()['pre_restore_backup_id']/'vehicles.db') as db:
                self.assertEqual(db.execute('SELECT value FROM example').fetchone()[0], 'after')

    def test_cleanup_preview_confirmation_and_only_old_files_removed(self):
        import os
        import time
        old = admin_api.CONTROL_CENTER_LOG_DIR/'old.log'
        recent = admin_api.CONTROL_CENTER_LOG_DIR/'recent.log'
        old.write_text('old synthetic log')
        recent.write_text('recent synthetic log')
        os.utime(old, (time.time()-40*86400, time.time()-40*86400))
        response = self.client.get('/admin-api/control-center/storage/cleanup-preview', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(old.exists())
        payload = {'confirm_text':'wrong','delete_old_logs_days':30,'delete_old_backups_days':30}
        self.assertEqual(self.client.post('/admin-api/control-center/storage/cleanup',headers=self.headers,json=payload).status_code,400)
        self.assertTrue(old.exists())
        payload['confirm_text'] = admin_api.CONTROL_CENTER_CLEANUP_CONFIRM
        result = self.client.post('/admin-api/control-center/storage/cleanup',headers=self.headers,json=payload)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['deleted_logs'],1)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())

    def test_automation_roundtrip_keeps_manual_run_separate_and_audits_changes(self):
        with tempfile.TemporaryDirectory(dir=jobs.DATA_DIR) as folder, patch.object(jobs, 'JOBS_STATE_FILE', Path(folder)/'jobs.json'), patch.dict('os.environ', {'ENABLE_REMINDER_NOTIFICATION_WORKER': '0'}):
            def status():
                response = self.client.get('/admin-api/control-center/jobs', headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                return next(row for row in response.json()['jobs'] if row['name'] == 'reminders.notification.check')
            def action(name):
                return self.client.post('/admin-api/control-center/jobs/'+name, headers=self.headers, json={'job_name': 'reminders.notification.check', 'reason': 'Isolated end-to-end verification'})
            self.assertFalse(status()['effective_enabled'])
            # Actual reminder processor on an empty database: no delivery involved.
            manual = action('run')
            self.assertEqual(manual.status_code, 200, manual.text)
            self.assertFalse(status()['effective_enabled'])
            self.assertEqual(action('resume').status_code, 200)
            self.assertTrue(status()['effective_enabled'])
            self.assertTrue(json.loads(jobs.JOBS_STATE_FILE.read_text())['enabled']['reminders.notification.check'])
            self.assertEqual(action('pause').status_code, 200)
            self.assertFalse(status()['effective_enabled'])
            self.assertEqual(action('run').status_code, 409)
            audit = self.client.get('/admin-api/control-center/audit-actions', headers=self.headers)
            self.assertEqual(audit.status_code, 200, audit.text)
            rows = [row for row in audit.json()['items'] if row['target_resource'] == 'reminders.notification.check']
            self.assertEqual([row['action_type'] for row in rows], ['jobs.pause', 'jobs.resume', 'jobs.run'])
            self.assertTrue(all(row['developer_email'] == 'operator-roundtrip@example.com' for row in rows))

    def test_admin_read_screens_return_serializable_http_results(self):
        paths = ['overview', 'users', 'services', 'service-registration-requests', 'vehicles', 'vehicles/duplicates', 'records', 'audit', 'db-info', 'settings',
                 'control-center/capabilities', 'control-center/health', 'control-center/payments', 'control-center/presence', 'control-center/access-accounts', 'control-center/access-history',
                 'control-center/security-monitor', 'control-center/backups', 'control-center/system-logs', 'control-center/webhook-monitor', 'control-center/storage', 'control-center/storage/cleanup-preview',
                 'control-center/api-monitor', 'control-center/email-monitor', 'control-center/debug-tools', 'control-center/jobs', 'control-center/notifications', 'control-center/audit-actions',
                 'users/'+str(self.admin_id)+'/detail', 'control-center/user-insight/'+str(self.admin_id)]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get('/admin-api/'+path, headers=self.headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNotNone(response.json())


if __name__ == '__main__':
    unittest.main()
