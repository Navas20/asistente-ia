"""
SECURITY LAYER - Autenticación y autorización
"""
import os
import logging
from functools import wraps
from fastapi import HTTPException, Header
from typing import Optional

from app.config import AUTH_TOKEN, ALLOWED_USER_IDS, ADMIN_IDS

log = logging.getLogger("artenisa.security")


def verify_token(token: Optional[str] = Header(None)):
    """Verifica el token de autorización"""
    if not token or token != AUTH_TOKEN:
        log.warning(f"Token inválido o ausente")
        raise HTTPException(status_code=401, detail="Token inválido o no autorizado")
    return token


def get_role(user_id: int) -> str:
    """Obtiene el rol del usuario"""
    if not ALLOWED_USER_IDS and not ADMIN_IDS:
        return "admin"
    if user_id in [int(uid) for uid in ADMIN_IDS if uid]:
        return "admin"
    if user_id in [int(uid) for uid in ALLOWED_USER_IDS if uid]:
        return "operator"
    return "denied"


def require_role(min_role: str = "operator"):
    """Decorator para verificar rol mínimo"""
    def decorator(func):
        @wraps(func)
        def wrapper(user_id: int, *args, **kwargs):
            role = get_role(user_id)
            if role == "denied":
                raise HTTPException(status_code=403, detail="No autorizado")
            if min_role == "admin" and role != "admin":
                raise HTTPException(status_code=403, detail="Se requiere rol admin")
            return func(user_id, *args, **kwargs)
        return wrapper
    return decorator
