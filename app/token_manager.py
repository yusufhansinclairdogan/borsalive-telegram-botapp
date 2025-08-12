# app/token_manager.py
from __future__ import annotations
import base64, json, threading, time
from typing import Optional

def _b64url_pad(s: str) -> bytes:
    return (s + "=" * ((4 - len(s) % 4) % 4)).encode()

def _jwt_exp(jwt: str) -> Optional[int]:
    try:
        parts = jwt.split(".")
        if len(parts) != 3:
            return None
        payload = json.loads(base64.urlsafe_b64decode(_b64url_pad(parts[1])))
        exp = payload.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None

class TokenManager:
    def __init__(self, initial_jwt: Optional[str] = None, renew_margin_sec: int = 120):
        self._lock = threading.RLock()
        self._jwt: Optional[str] = initial_jwt
        self._exp: Optional[int] = _jwt_exp(initial_jwt) if initial_jwt else None
        self._renew_margin = renew_margin_sec  # exp-120s kalınca geçersiz say
    def set(self, jwt: str) -> None:
        with self._lock:
            self._jwt = jwt
            self._exp = _jwt_exp(jwt)
    def get(self) -> Optional[str]:
        with self._lock:
            if not self._jwt:
                return None
            if self._exp is None:
                return self._jwt
            now = int(time.time())
            if self._exp - now <= self._renew_margin:
                # Süresi bitmek üzere: çağıran taraf yeniden /admin/jwt ile güncellemeli
                return None
            return self._jwt
    def info(self) -> dict:
        with self._lock:
            return {"has_jwt": bool(self._jwt), "exp": self._exp}
