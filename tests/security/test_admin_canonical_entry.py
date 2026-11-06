"""Public HTTPS terminates at the proxy while Starlette receives HTTP."""
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.server.web_access import router


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_admin_entry_uses_public_scheme_and_preserves_query(method):
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, base_url='http://proxy-internal') as client:
        result = client.request(method, '/web_admin?section=messages', follow_redirects=False,
                                headers={'host': 'app.toozservis.cz', 'x-forwarded-proto': 'https',
                                         'x-forwarded-host': 'untrusted.example'})
    assert result.status_code == 307
    assert result.headers['location'] == '/web_admin/?section=messages'
    assert urljoin('https://app.toozservis.cz/web_admin', result.headers['location']) == 'https://app.toozservis.cz/web_admin/?section=messages'
