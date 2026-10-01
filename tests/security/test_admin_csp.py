"""Both admin aliases and the sign-in script receive the strict browser policy."""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from src.core.browser_policy import ADMIN_CONTENT_SECURITY_POLICY
from src.core.security_middleware import SecurityHeadersMiddleware
from src.server.web_access import router


def test_admin_policy_on_login_and_dashboard_aliases():
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(SecurityHeadersMiddleware)
    @app.get('/{path:path}')
    def page(path: str):
        return HTMLResponse('<h1>fixture</h1>')
    with TestClient(app) as client:
        for path in ['/admin-login','/admin-login.js','/admin-session.js','/web_admin/','/web_admin/index.html','/admin-static/index.html']:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers['content-security-policy'] == ADMIN_CONTENT_SECURITY_POLICY
            assert response.headers['x-frame-options'] == 'DENY'
            assert response.headers['cache-control'] == 'no-store'
        html=client.get('/admin-login').text
        assert '<script src="/admin-login.js"></script>' in html
        assert '<script>' not in html
        script=client.get('/admin-login.js')
        assert 'javascript' in script.headers['content-type']
        assert "form.addEventListener('submit'" in script.text
    assert "script-src-attr 'none'" in ADMIN_CONTENT_SECURITY_POLICY
    assert "script-src 'self';" in ADMIN_CONTENT_SECURITY_POLICY
    assert "form-action 'self'" in ADMIN_CONTENT_SECURITY_POLICY


def test_compatibility_dashboard_policy_blocks_scripts_and_embedding():
    from src.core.browser_policy import LEGACY_ADMIN_CONTENT_SECURITY_POLICY
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    @app.get('/{path:path}')
    def page(path: str):
        return HTMLResponse('<h1>fixture</h1>')
    with TestClient(app) as client:
        for path in ['/web', '/web/', '/web/index.html', '/web//index.html']:
            response = client.get(path)
            assert response.headers['content-security-policy'] == LEGACY_ADMIN_CONTENT_SECURITY_POLICY
            assert response.headers['x-frame-options'] == 'DENY'
            assert response.headers['cache-control'] == 'no-store'
    assert "script-src 'self'; script-src-attr 'none'" in LEGACY_ADMIN_CONTENT_SECURITY_POLICY
    assert "connect-src 'self'" in LEGACY_ADMIN_CONTENT_SECURITY_POLICY
    assert "frame-src blob:" in LEGACY_ADMIN_CONTENT_SECURITY_POLICY
