from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.server.web_access import router, AdminStaticFiles, PUBLIC_WEB_PAGES
from src.core.browser_policy import LEGACY_ADMIN_CONTENT_SECURITY_POLICY


def test_public_customer_shell_keeps_admin_and_backups_private():
    app = FastAPI()
    app.include_router(router)
    app.mount('/web', AdminStaticFiles(directory='web', public_pages=PUBLIC_WEB_PAGES))
    with TestClient(app) as client:
        page = client.get('/web/customer.html')
        worker = client.get('/web/customer-sw.js')
        assert worker.status_code == 200
        assert '/web/customer.html' in worker.text
        assert "url.origin === self.location.origin" in worker.text
        assert page.status_code == 200
        assert '/web/customer-session.js' in page.text
        assert '/admin-session.js' not in page.text
        assert page.headers['content-security-policy'] == LEGACY_ADMIN_CONTENT_SECURITY_POLICY
        assert page.headers['cache-control'] == 'no-store'
        for asset in ['customer-session.js','customer-features.js','service-features.js','vendor/jsQR-1.4.0.js','customer.css','legacy-app.js','legacy-actions.js','legacy-lookups.js','theme.css','app.css','inline-styles.css']:
            assert client.get('/web/'+asset).status_code == 200
        for private in ['index.html', 'index.html.backup_now', 'index_minimal.html']:
            assert client.get('/web/'+private, follow_redirects=False).status_code == 303
