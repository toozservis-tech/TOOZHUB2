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


def test_safe_diagnostics_do_not_format_exceptions_or_source(capsys):
    from src.core.private_errors import report_exception, incident_id
    class ProviderFailure(RuntimeError):
        def __str__(self):
            raise AssertionError('Provider exception must never be stringified')
        __repr__ = __str__
    try:
        raise ProviderFailure('synthetic-password', {'private': 'synthetic-personal-data'})
    except ProviderFailure as original:
        reference = report_exception(original)
        try:
            raise RuntimeError('synthetic-token') from original
        except RuntimeError as wrapped:
            assert incident_id(wrapped) == reference
            report_exception(wrapped)
    output = capsys.readouterr()
    assert reference in output.out
    assert 'test_safe_diagnostics_do_not_format_exceptions_or_source' in output.out
    for secret in ['synthetic-password','synthetic-personal-data','synthetic-token','Provider exception must']:
        assert secret not in output.out + output.err


def test_admin_query_failures_are_not_successful_empty_data_or_secret_logs(capsys):
    from unittest.mock import Mock
    from sqlalchemy.exc import StatementError
    from src.server import admin_api
    from src.modules.vehicle_hub.database import get_db
    app=FastAPI();app.include_router(admin_api.router);_register_exception_handler(app)
    db=Mock()
    db.execute.side_effect=StatementError('provider-secret', 'SELECT secret FROM private', {'password':'synthetic-password'}, RuntimeError('synthetic-pii'))
    app.dependency_overrides[get_db]=lambda:db
    app.dependency_overrides[admin_api.require_developer_admin]=lambda:'synthetic-admin@example.invalid'
    with TestClient(app) as client:
        for path in ['/admin-api/overview','/admin-api/records','/admin-api/audit']:
            r=client.get(path)
            assert r.status_code==500, r.text
            assert r.json()['incident_id']
            captured=capsys.readouterr()
            combined=r.text+captured.out+captured.err
            for value in ['provider-secret','SELECT secret','synthetic-password','synthetic-pii']:
                assert value not in combined
            assert r.json()['incident_id'] in captured.out
