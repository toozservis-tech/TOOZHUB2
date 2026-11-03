from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.server.web_access import router, AdminStaticFiles, PUBLIC_WEB_PAGES
from src.core.browser_policy import LEGACY_ADMIN_CONTENT_SECURITY_POLICY
from unittest.mock import patch
from fastapi import HTTPException


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
        assert page.text.index('src="job-timeline.js"') < page.text.index('src="customer-features.js"')
        for asset in ['customer-session.js','customer-features.js','service-features.js','vendor/jsQR-1.4.0.js','customer.css','legacy-app.js','legacy-actions.js','legacy-lookups.js','theme.css','app.css','inline-styles.css']:
            assert client.get('/web/'+asset).status_code == 200
        for private in ['index.html', 'index.html.backup_now', 'index_minimal.html']:
            assert client.get('/web/'+private, follow_redirects=False).status_code == 303


def test_referral_assets_are_exact_public_exceptions(tmp_path):
    assets = ['referral-registration.js', 'referral-features.js',
              'referral-features.css', 'vendor/referral-qr.js', 'job-timeline.js']
    private = ['index.html', 'admin/referral-features.js',
               'referral-features.js.bak', 'referral-features.js.map']
    for name in assets + private:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('synthetic asset', encoding='utf-8')
    app = FastAPI()
    app.mount('/web', AdminStaticFiles(directory=tmp_path, public_pages=PUBLIC_WEB_PAGES))
    with TestClient(app) as client, patch(
        'src.server.web_access.require_web_admin', side_effect=HTTPException(401)
    ) as gate:
        for asset in assets:
            response = client.get('/web/' + asset, follow_redirects=False)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
        gate.assert_not_called()
        for name in private:
            assert client.get('/web/' + name, follow_redirects=False).status_code == 303
        assert gate.call_count == len(private)
