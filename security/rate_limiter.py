"""
SECURITY LAYER - Rate Limiting
"""
import time
import threading
import logging
from functools import wraps
from fastapi import HTTPException

from app.config import RATE_LIMIT_CALLS, RATE_LIMIT_WINDOW

log = logging.getLogger("artenisa.security")


class RateLimiter:
    """Rate limiter en memoria con buckets por clave"""
    
    def __init__(self):
        self._buckets = {}
        self._lock = threading.Lock()
    
    def check(self, key: str, max_calls: int = RATE_LIMIT_CALLS, window: int = RATE_LIMIT_WINDOW):
        """Verifica si se puede hacer la llamada"""
        now = time.time()
        
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = {"calls": [], "blocked_until": 0}
            
            bucket = self._buckets[key]
            
            # Si está bloqueado
            if bucket["blocked_until"] > now:
                reset_after = int(bucket["blocked_until"] - now)
                return (False, 0, reset_after)
            
            # Limpia calls antiguos
            cutoff = now - window
            bucket["calls"] = [t for t in bucket["calls"] if t > cutoff]
            
            # Si excedió límite
            if len(bucket["calls"]) >= max_calls:
                bucket["blocked_until"] = now + 30
                return (False, 0, 30)
            
            # Registra nueva llamada
            bucket["calls"].append(now)
            remaining = max_calls - len(bucket["calls"])
            oldest = bucket["calls"][0] if bucket["calls"] else now
            reset_after = max(0, int(window - (now - oldest)))
            
            return (True, remaining, reset_after)
    
    def wrap(self, max_calls: int = RATE_LIMIT_CALLS, window: int = RATE_LIMIT_WINDOW):
        """Decorator para rate limiting"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                authorization = kwargs.get("authorization", func.__name__)
                allowed, remaining, reset_after = self.check(authorization, max_calls, window)
                
                if not allowed:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Límite de peticiones excedido. Reintenta en {reset_after}s"
                    )
                
                response = func(*args, **kwargs)
                
                # Agrega headers de rate limit
                if hasattr(response, "headers"):
                    response.headers["X-RateLimit-Remaining"] = str(remaining)
                    response.headers["X-RateLimit-Reset"] = str(reset_after)
                
                return response
            
            return wrapper
        return decorator


# Instancia global
limiter = RateLimiter()
