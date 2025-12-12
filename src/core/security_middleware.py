"""
Security Middleware pro TooZ Hub 2
- Security headers
- Rate limiting
- Anti-tampering
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable
import time
from collections import defaultdict
from datetime import datetime, timedelta
from src.core.config import ALLOWED_ORIGINS, ENVIRONMENT

# Rate limiting - ukládání požadavků
rate_limit_store = defaultdict(list)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware pro přidání security headers"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers - povinné základní ochrana
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        
        # HSTS - pouze pro HTTPS
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        
        # Content Security Policy - CSP hlavně pro ochranu proti embedování z jiných webů
        # TooZ Hub 2 se embeduje do Webnode jen z těchto domén:
        # - https://www.toozservis.cz
        # - https://toozservis.cz
        if ENVIRONMENT == "production":
            # Produkce: povolit pouze toozservis.cz domény (bez hub.toozservis.cz - nechceme, aby se embedoval sám do sebe)
            frame_ancestors = "https://www.toozservis.cz https://toozservis.cz"
        else:
            # Development: povolit všechny (pro testování)
            frame_ancestors = "*"
        
        # CSP - kompatibilní se stávajícími skripty
        if ENVIRONMENT == "production":
            # Produkce: povolit embed jen z toozservis.cz domén
            csp = (
                "default-src 'self'; "
                "img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'self' https://www.toozservis.cz https://toozservis.cz;"
            )
        else:
            # Development: povolit všechny (pro testování)
            csp = (
                "default-src 'self'; "
                "img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "frame-ancestors *;"
            )
        
        # Nenahrazuj existující CSP, pokud už existuje
        if "content-security-policy" not in (k.lower() for k in response.headers.keys()):
            response.headers["Content-Security-Policy"] = csp
        
        # Hide server info
        response.headers["Server"] = "TooZ Hub"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware pro rate limiting"""
    
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls  # Počet požadavků
        self.period = period  # Období v sekundách
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Získat IP adresu
        client_ip = request.client.host if request.client else "unknown"
        
        # Získat endpoint
        endpoint = request.url.path
        
        # Vytvořit klíč pro rate limiting
        key = f"{client_ip}:{endpoint}"
        
        # Vyčistit staré záznamy
        now = time.time()
        rate_limit_store[key] = [
            timestamp for timestamp in rate_limit_store[key]
            if now - timestamp < self.period
        ]
        
        # Kontrola limitu
        if len(rate_limit_store[key]) >= self.calls:
            return Response(
                content='{"detail":"Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json"
            )
        
        # Přidat aktuální požadavek
        rate_limit_store[key].append(now)
        
        # Pokračovat
        response = await call_next(request)
        
        # Přidat rate limit headers
        remaining = self.calls - len(rate_limit_store[key])
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + self.period))
        
        return response


class AntiTamperingMiddleware(BaseHTTPMiddleware):
    """Middleware pro detekci manipulace s požadavky"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Kontrola podezřelých headers
        suspicious_headers = [
            "x-forwarded-for",
            "x-real-ip",
            "x-originating-ip",
            "x-remote-ip",
            "x-remote-addr"
        ]
        
        # Log podezřelých požadavků (v produkci)
        for header in suspicious_headers:
            if header in request.headers:
                print(f"[SECURITY] Suspicious header detected: {header} = {request.headers[header]}")
        
        response = await call_next(request)
        
        # Přidat anti-tampering headers
        response.headers["X-Request-ID"] = str(int(time.time() * 1000))
        
        return response

