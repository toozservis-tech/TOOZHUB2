"""Private durable file storage; local DATA_DIR is only a cache in cloud mode."""
import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path
import httpx
from fastapi import HTTPException
from src.core.config import DATA_DIR


def _key(path: Path) -> str:
    relative = path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
    return 'assets/' + hashlib.sha256(relative.encode('utf-8')).hexdigest()


def _config():
    base = os.getenv('SUPABASE_URL', '').rstrip('/')
    key = os.getenv('SUPABASE_SECRET_KEY', '')
    if not base and not key:
        return None
    if not base.startswith('https://') or not key:
        raise RuntimeError('Incomplete private storage configuration')
    return base+'/storage/v1/object/'+os.getenv('SUPABASE_STORAGE_BUCKET','toozhub-private')+'/', {'apikey':key}


def _atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f: f.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def persist_file(path: Path, content: bytes, *, replace=False):
    object_key = _key(path)  # Reject writes outside the managed storage root.
    config = _config()
    if config:
        base, headers = config
        try:
            r = httpx.post(base+object_key, headers={**headers, 'Content-Type':mimetypes.guess_type(path.name)[0] or 'application/octet-stream', 'x-upsert':str(replace).lower()}, content=content, timeout=45)
            r.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(503, 'Soubor se nepodařilo bezpečně uložit. Zkuste to znovu.') from None
    _atomic(path, content)


def require_persisted_file(path: Path) -> None:
    """Check a new committed reference against durable storage, never stale cache.

    Authorization and vehicle/path boundaries are the caller's responsibility.
    In cloud mode a local file is not evidence of a successful durable upload.
    Read only the first response chunk and do not populate the cache.
    """
    object_key = _key(path)
    config = _config()
    unavailable = 'Příloha nebyla nalezena v úložišti. Nahrajte ji prosím znovu.'
    if not config:
        if not path.is_file() or path.stat().st_size == 0:
            raise HTTPException(409, unavailable)
        return
    base, headers = config
    try:
        with httpx.stream('GET', base + object_key, headers=headers, timeout=20,
                          follow_redirects=False) as response:
            if response.status_code in (400, 404):
                response.read()
                body = response.json()
                if isinstance(body, dict) and (str(body.get('statusCode')) == '404'
                        or body.get('error') in ('not_found', 'Not Found')):
                    raise HTTPException(409, unavailable)
            response.raise_for_status()
            if response.status_code != 200:
                raise HTTPException(503, 'Úložiště souborů nyní nelze ověřit. Zkuste to později.')
            if not next(response.iter_bytes(chunk_size=1), b''):
                raise HTTPException(409, unavailable)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'Úložiště souborů nyní nelze ověřit. Zkuste to později.') from None


def cached_file(path: Path, *, refresh=False) -> Path:
    object_key = _key(path)
    config = _config()
    if not config or (path.is_file() and not refresh):
        return path
    base, headers = config
    try:
        r = httpx.get(base+object_key,headers=headers,timeout=45)
        if r.status_code in (400,404):
            # Only the known missing-object response is treated as absence.
            body=r.json()
            if str(body.get('statusCode'))=='404' or body.get('error') in ('not_found','Not Found'):
                return path
        r.raise_for_status()
        _atomic(path, r.content)
    except (httpx.HTTPError,ValueError):
        raise HTTPException(503, 'Úložiště souborů není dostupné. Zkuste to znovu.') from None
    return path
