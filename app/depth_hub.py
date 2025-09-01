import asyncio
from typing import Dict, List, Any
from time import time

class DepthHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._store: Dict[str, Dict[str, Any]] = {}

    async def set(self, symbol: str, levels: List[Dict[str, Any]]) -> None:
        async with self._lock:
            self._store[symbol] = {"levels": levels, "ts": int(time()*1000)}

    async def get_last(self, symbol: str, timeout: float = 0.0):
        # timeout param’ı API uyumu için; burada kullanılmıyor
        async with self._lock:
            d = self._store.get(symbol)
            return d["levels"] if d else []

    async def get_ts(self, symbol: str):
        async with self._lock:
            d = self._store.get(symbol)
            return d["ts"] if d else None

hub = DepthHub()
