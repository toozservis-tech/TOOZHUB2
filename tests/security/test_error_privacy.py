"""No credentials in error responses or our exception-boundary logs."""
import contextlib
import io
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from src.server.bootstrap import _register_exception_handler


def test_unhandled_and_handled_errors_do_not_return_provider_data():
    app=FastAPI();_register_exception_handler(app)
    private='private-provider-password-and-personal-data'
    @app.get('/unhandled')
    def unhandled(): raise RuntimeError(private)
    @app.get('/handled')
    def handled(): raise HTTPException(500,private)
    @app.get('/admin-expired')
    def admin_expired(): raise HTTPException(403,'Ověření je nutné',headers={'X-Admin-Verification':'required'})
    with contextlib.redirect_stdout(io.StringIO()) as out, TestClient(app) as client:
        for path in ['/unhandled','/handled']:
            r=client.get(path);assert r.status_code==500
            assert private not in r.text
            assert len(r.json()['incident_id'])==32
            assert r.headers['Cache-Control']=='no-store'
        r=client.get('/admin-expired');assert r.status_code==403
        assert r.headers['X-Admin-Verification']=='required'
    assert private not in out.getvalue()
    assert 'incident=' in out.getvalue()


def test_export_allowlist_excludes_future_and_known_sensitive_fields():
    from src.modules.vehicle_hub.export_privacy import EXPORT_FIELDS, export_fields
    prohibited={'password_hash','totp_secret','token','reset_token','auth','p256dh','endpoint','error_message','last_error','details'}
    for fields in EXPORT_FIELDS.values():
        assert not prohibited.intersection(fields)
    import pytest
    with pytest.raises(ValueError): export_fields(object())
