"""Browser UI is admin-only. Mobile APIs keep their bearer authorization."""
from pathlib import Path
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from src.core.security import decode_access_token_payload
from src.modules.vehicle_hub.database import SessionLocal, get_db
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.account_state import customer_is_deleted, customer_is_disabled, customer_session_version

PUBLIC_WEB_PAGES = {
    "open-app.html", "payment-return.html", "assets/mastercard-mark.svg", "chatbot/widget.js", "chatbot/robot-logo.png",
    "reset-password.html", "verify-email.html", "cookies.html", "obchodni-podminky.html",
    "ochrana-osobnich-udaju.html", "platebni-podminky.html", "reklamacni-rad.html",
    "assets/apple-pay-official.svg", "assets/google-pay-official.svg",
    "assets/mastercard-official.svg", "assets/visa-official.svg",
    "assets/comgate-logo-horizontal-red.png", "assets/toozservis-logo-icon.png",
}
router = APIRouter()
COOKIE = 'admin_web_session'

def require_web_admin(token, db):
    payload = decode_access_token_payload(token or '')
    if not payload:
        raise HTTPException(401, 'Přihlaste se jako administrátor.')
    user = db.query(Customer).filter(func.lower(Customer.email) == str(payload.get('sub', '')).lower()).first()
    if not user or customer_is_deleted(user) or customer_is_disabled(user):
        raise HTTPException(401, 'Přihlášení již není platné.')
    if str(payload.get('sv', 0)) != str(customer_session_version(user)):
        raise HTTPException(401, 'Přihlášení již není platné.')
    if user.role not in {'admin', 'developer_admin'}:
        raise HTTPException(403, 'Webové rozhraní je dostupné pouze administrátorům. Použijte aplikaci Správa vozidel.')
    return payload

@router.get('/admin-login', include_in_schema=False)
def admin_login():
    return FileResponse(Path(__file__).with_name('admin_login.html'), headers={'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow'})

@router.post('/admin-web-session', include_in_schema=False)
def open_session(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), db: Session = Depends(get_db)):
    payload = require_web_admin(credentials.credentials, db)
    response = JSONResponse({'ok': True}, headers={'Cache-Control':'no-store'})
    response.set_cookie(COOKIE, credentials.credentials, httponly=True, secure=True, samesite='strict', path='/', max_age=max(1, min(3600, int(payload['exp'] - time.time()))))
    return response

@router.delete('/admin-web-session', include_in_schema=False)
def close_session():
    response = JSONResponse({'ok': True}, headers={'Cache-Control':'no-store'})
    response.delete_cookie(COOKIE, path='/', secure=True, httponly=True, samesite='strict')
    return response

class AdminStaticFiles(StaticFiles):
    def __init__(self, *args, public_pages=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.public_pages = set(public_pages)

    async def get_response(self, path, scope):
        # Explicit exceptions are only standalone account-recovery pages.
        if path not in self.public_pages:
            request = Request(scope)
            token = request.cookies.get(COOKIE)
            def check():
                with SessionLocal() as db:
                    require_web_admin(token, db)
            try:
                await run_in_threadpool(check)
            except HTTPException as exc:
                if exc.status_code == 401:
                    return RedirectResponse('/admin-login', status_code=303, headers={'Cache-Control':'no-store'})
                return JSONResponse({'detail':exc.detail}, status_code=403, headers={'Cache-Control':'no-store'})
        # Never expose backups of frontend source.
        if path.endswith(('.bak', '.map')):
            raise HTTPException(404)
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
