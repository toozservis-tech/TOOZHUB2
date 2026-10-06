"""Browser UI is admin-only. Mobile APIs keep their bearer authorization."""
from pathlib import Path
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from src.core.security import decode_access_token_payload
from src.core.session_revocation import require_active_token, revoke_tokens
from src.modules.vehicle_hub.database import SessionLocal, get_db
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.account_state import customer_is_deleted, customer_is_disabled, customer_session_version
from src.modules.vehicle_hub.email_verification import pending_verification

PUBLIC_WEB_PAGES = {
    "customer-session.js", "customer.css", "customer-features.js", "service-features.js", "vendor/jsQR-1.4.0.js", "assets/auth-seq-step1-vehicles.png", "assets/auth-seq-step2-add-vehicle.png", "assets/auth-seq-step4-reservations.png", "legacy-actions.js", "legacy-app.js", "legacy-lookups.js",
    "storage_migration.js", "ai-features.js", "theme.css", "app.css", "inline-styles.css",
    "service-invitation.html",
    "reservations.html",
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
    require_active_token(db, token)
    user = db.query(Customer).filter(func.lower(Customer.email) == str(payload.get('sub', '')).lower()).first()
    if not user or customer_is_deleted(user) or customer_is_disabled(user):
        raise HTTPException(401, 'Přihlášení již není platné.')
    if str(payload.get('sv', 0)) != str(customer_session_version(user)):
        raise HTTPException(401, 'Přihlášení již není platné.')
    if user.role not in {'admin', 'developer_admin'}:
        raise HTTPException(403, 'Webové rozhraní je dostupné pouze administrátorům. Použijte aplikaci Evidence Vozidel.')
    if pending_verification(db, user.id):
        raise HTTPException(403, 'Nejprve ověřte svou e-mailovou adresu v aplikaci.')
    from src.core.mfa import require_admin_assurance
    require_admin_assurance(db, user, payload)
    return payload

@router.get('/web/customer-sw.js', include_in_schema=False)
def customer_worker():
    from fastapi.responses import Response
    source = Path(__file__).resolve().parents[2] / 'web' / 'sw.js'
    script = source.read_text().replace('/web/index.html', '/web/customer.html')
    # Existing notification payloads may still carry the compatibility route.
    script = script.replace("return url.href;", "return url.pathname === '/web/index.html' ? new URL('/web/customer.html' + url.search, self.location.origin).href : url.href;")
    return Response(script, media_type='text/javascript', headers={'Cache-Control': 'no-store'})

@router.get('/web/customer.html', include_in_schema=False)
def customer_web():
    # Reuse the maintained UI, but never expose the administrator session.
    from src.core.browser_policy import LEGACY_ADMIN_CONTENT_SECURITY_POLICY
    source = Path(__file__).resolve().parents[2] / 'web' / 'index.html'
    html = source.read_text().replace('<title>Evidence Vozidel</title>', '<title>Evidence Vozidel – webová aplikace</title>').replace('/admin-session.js', '/web/customer-session.js')
    html = html.replace('</head>', '<link rel="stylesheet" href="customer.css"></head>')
    html = html.replace('</body>', '<script src="vendor/jsQR-1.4.0.js"></script><script src="customer-features.js"></script><script src="service-features.js"></script></body>')
    html = html.replace('Po zadání 8 číslic se automaticky načtou údaje z ARES.', 'Firemní údaje nyní vyplňte ručně. Načítání z ARES je dostupné po přihlášení.')
    html = html.replace('Ověřuji přihlášení administrátora…', 'Načítám Evidence Vozidel…')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store', 'Content-Security-Policy': LEGACY_ADMIN_CONTENT_SECURITY_POLICY, 'X-Frame-Options': 'DENY'})

@router.get('/admin-login', include_in_schema=False)
def admin_login():
    return FileResponse(Path(__file__).with_name('admin_login.html'), headers={'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow'})

@router.get('/admin-login.js', include_in_schema=False)
def admin_login_script():
    return FileResponse(Path(__file__).with_name('admin_login.js'), media_type='text/javascript', headers={'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow'})

@router.get('/admin-session.js', include_in_schema=False)
def admin_session_script():
    return FileResponse(Path(__file__).with_name('admin_session.js'), media_type='text/javascript', headers={'Cache-Control':'no-store', 'X-Robots-Tag':'noindex, nofollow'})

@router.post('/admin-web-session', include_in_schema=False)
def open_session(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()), db: Session = Depends(get_db)):
    payload = require_web_admin(credentials.credentials, db)
    response = JSONResponse({'ok': True}, headers={'Cache-Control':'no-store'})
    response.set_cookie(COOKIE, credentials.credentials, httponly=True, secure=True, samesite='strict', path='/', max_age=max(1, min(3600, int(payload['exp'] - time.time()))))
    return response

@router.delete('/admin-web-session', include_in_schema=False)
def close_session(request: Request, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)), db: Session = Depends(get_db)):
    cookie = request.cookies.get(COOKIE)
    token = credentials.credentials if credentials else cookie
    revoke_tokens(db, [token])
    response = JSONResponse({'ok': True}, headers={'Cache-Control':'no-store'})
    # Never send a cookie deletion for bearer logout: even a matching request
    # cookie may have been replaced while this response was in flight. The
    # revoked cookie is harmless and the next login will overwrite it.
    if not credentials:
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
                if exc.status_code == 401 or (exc.headers or {}).get('X-Admin-Verification'):
                    return RedirectResponse('/admin-login', status_code=303, headers={'Cache-Control':'no-store'})
                return JSONResponse({'detail':exc.detail}, status_code=403, headers={'Cache-Control':'no-store'})
        # Never expose backups of frontend source.
        if path.endswith(('.bak', '.map')):
            raise HTTPException(404)
        response = await super().get_response(path, scope)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
