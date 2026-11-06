"""Exact static whitelist, real AdminStaticFiles class. No database/API/browser mutation.
Authentication gate is a denying stub; this checks dispatch to the gate, not real login.
"""
import ast
from pathlib import Path
from contextlib import nullcontext
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[2]


def test_public_booking_asset_only_with_unchanged_private_gate():
    tree = ast.parse((ROOT / 'src/server/web_access.py').read_text())
    declarations = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AdminStaticFiles'
                    or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PUBLIC_WEB_PAGES' for t in n.targets)]
    hits = []
    def deny(token, db):
        hits.append(token)
        raise HTTPException(401)
    env = dict(StaticFiles=StaticFiles, Request=Request, COOKIE='admin_web_session',
               SessionLocal=lambda: nullcontext(None), require_web_admin=deny,
               run_in_threadpool=run_in_threadpool, HTTPException=HTTPException,
               RedirectResponse=RedirectResponse, JSONResponse=JSONResponse)
    exec(compile(ast.Module(body=declarations, type_ignores=[]), 'web_access.py', 'exec'), env)
    app = FastAPI()
    app.mount('/web', env['AdminStaticFiles'](directory=ROOT / 'web', public_pages=env['PUBLIC_WEB_PAGES']))
    with TestClient(app) as client:
        response = client.get('/web/booking-requests.js')
        assert response.status_code == 200
        assert response.content == (ROOT / 'web/booking-requests.js').read_bytes()
        assert 'javascript' in response.headers['content-type']
        assert response.headers['cache-control'] == 'no-store'
        assert hits == []
        for path in ['index.html','booking-requests.js.bak','booking-requests.js.map','admin/booking-requests.js']:
            assert client.get('/web/'+path, follow_redirects=False).status_code == 303
        assert len(hits) == 4
    assert '/api/v1/service-booking-requests' not in env['PUBLIC_WEB_PAGES']
