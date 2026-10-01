"""Durability checks must not mistake a warm local cache for a cloud upload."""
import hashlib

from fastapi import HTTPException
import httpx
import pytest

from src.core import file_storage as storage


@pytest.fixture
def cloud(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(storage, '_config', lambda: ('https://storage.example/private/', {'apikey': 'test-key'}))
    path = tmp_path/'service_record_attachments/tenant_1/vehicle_1/file.pdf'
    path.parent.mkdir(parents=True); path.write_bytes(b'OLD LOCAL COPY')
    return path


def use_response(monkeypatch, responder):
    client = httpx.Client(transport=httpx.MockTransport(responder))
    monkeypatch.setattr(storage.httpx, 'stream', client.stream)
    return client


@pytest.mark.parametrize('status', [400, 404])
def test_cloud_missing_file_is_rejected_even_when_cached_locally(cloud, monkeypatch, status):
    with use_response(monkeypatch, lambda request: httpx.Response(status, json={'statusCode': '404', 'error': 'not_found'})):
        with pytest.raises(HTTPException) as error:
            storage.require_persisted_file(cloud)
    assert error.value.status_code == 409
    assert cloud.read_bytes() == b'OLD LOCAL COPY', 'Check cannot erase original local evidence'


@pytest.mark.parametrize('status', [401, 403, 429, 500, 302])
def test_provider_failure_never_accepts_stale_cache_or_leaks_server_details(cloud, monkeypatch, status):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(status, text='private provider details', headers={'Location': 'https://outside.example'})
    with use_response(monkeypatch, respond):
        with pytest.raises(HTTPException) as error:
            storage.require_persisted_file(cloud)
    assert error.value.status_code == 503
    assert len(seen) == 1, 'Private credentials must not be redirected'
    assert 'private provider details' not in error.value.detail and 'test-key' not in error.value.detail


def test_live_cloud_file_is_checked_without_caching_or_downloading_the_full_document(cloud, monkeypatch):
    reads = []
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            reads.append('first'); yield b'LIVE CONTENT'
            pytest.fail('Durability check must stop without reading the rest of the document')
    def respond(request):
        assert request.headers['apikey'] == 'test-key'
        expected = hashlib.sha256(b'service_record_attachments/tenant_1/vehicle_1/file.pdf').hexdigest()
        assert request.url.path == '/private/assets/'+expected
        return httpx.Response(200, stream=Body())
    with use_response(monkeypatch, respond):
        storage.require_persisted_file(cloud)
    assert reads == ['first'] and cloud.read_bytes() == b'OLD LOCAL COPY'


def test_empty_remote_file_is_not_an_uploaded_attachment(cloud, monkeypatch):
    with use_response(monkeypatch, lambda request: httpx.Response(200, content=b'')):
        with pytest.raises(HTTPException) as error: storage.require_persisted_file(cloud)
    assert error.value.status_code == 409


def test_local_mode_requires_an_existing_nonempty_regular_file(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(storage, '_config', lambda: None)
    path = tmp_path/'photo.jpg'
    for state in ('missing', 'empty', 'directory'):
        if state == 'empty': path.write_bytes(b'')
        if state == 'directory': path.unlink(); path.mkdir()
        with pytest.raises(HTTPException) as error: storage.require_persisted_file(path)
        assert error.value.status_code == 409
    path.rmdir(); path.write_bytes(b'SYNTHETIC IMAGE'); storage.require_persisted_file(path)
