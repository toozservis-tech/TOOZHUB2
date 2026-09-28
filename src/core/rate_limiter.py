"""
Rate Limiter pro API endpointy
Ochrana proti DDoS a brute force útokům
"""
from functools import wraps
from fastapi import HTTPException, Request
from typing import Callable
from collections import defaultdict
import time
from threading import RLock
from datetime import datetime, timedelta


class RateLimiter:
    """Jednoduchý rate limiter"""
    
    def __init__(self):
        self.storage = defaultdict(list)
        self._lock = RLock()
        self._last_cleanup = 0.0
    
    def check_rate_limit(
        self,
        key: str,
        max_calls: int,
        period: int = 60
    ) -> bool:
        """
        Zkontroluje, zda byl překročen rate limit.
        
        Args:
            key: Unikátní klíč (např. IP adresa nebo email)
            max_calls: Maximální počet volání
            period: Období v sekundách
        
        Returns:
            True pokud je limit v pořádku, False pokud byl překročen
        """
        with self._lock:
            now = time.monotonic()
            if now - self._last_cleanup > 60:
                # Auth windows are at most one day. Bound stale key retention.
                stale = [k for k, v in self.storage.items() if not v or now - v[-1] > 86400]
                for old_key in stale:
                    del self.storage[old_key]
                self._last_cleanup = now
            if key not in self.storage and len(self.storage) >= 50000:
                return False
            self.storage[key] = [t for t in self.storage[key] if now - t < period]
            if len(self.storage[key]) >= max_calls:
                return False
            self.storage[key].append(now)
            return True

    def clear(self, key: str = None):
        """Vyčistí rate limit pro klíč nebo všechny"""
        if key:
            if key in self.storage:
                del self.storage[key]
        else:
            self.storage.clear()


# Globální instance
rate_limiter = RateLimiter()


def rate_limit(max_calls: int = 5, period: int = 60, key_func: Callable = None):
    """
    Decorator pro rate limiting endpointu.
    
    Args:
        max_calls: Maximální počet volání
        period: Období v sekundách
        key_func: Funkce pro získání klíče (výchozí: IP adresa)
    
    Note: Pro FastAPI endpointy použijte Depends místo tohoto decoratoru
    nebo použijte RateLimitMiddleware.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Získat klíč pro rate limiting
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Výchozí: použít IP adresu z requestu (pokud je k dispozici)
                key = "global"  # Fallback
            
            # Kontrola rate limitu
            if not rate_limiter.check_rate_limit(key, max_calls, period):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {max_calls} requests per {period} seconds."
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator




