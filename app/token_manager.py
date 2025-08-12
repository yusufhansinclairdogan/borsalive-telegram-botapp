# app/token_manager.py
import base64
import json
import time
from typing import Optional

def _jwt_exp(jwt_str: str) -> Optional[int]:
    try:
        parts = jwt_str.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=="  # base64url pad
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return int(data.get("exp")) if "exp" in data else None
    except Exception:
        return None

class TokenManager:
    def __init__(self, initial_jwt: str = ""):
        self._jwt = initial_jwt
        self._exp = _jwt_exp(initial_jwt) if initial_jwt else None

    def get(self) -> Optional[str]:
        if not self._jwt:
            return None
        if self._exp and time.time() > self._exp - 30:  # 30 sn önce yenilenmeli
            return None
        return self._jwt

    def set(self, jwt_str: str):
        self._jwt = jwt_str
        self._exp = _jwt_exp(jwt_str)
