# app/trade_hub.py
import asyncio
from collections import deque
from typing import Dict, Deque, Any, List


class TradeHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._store: Dict[str, Deque[Dict[str, Any]]] = {}

    async def add(self, symbol: str, trade: Dict[str, Any]) -> None:
        async with self._lock:
            dq = self._store.setdefault(symbol, deque(maxlen=400))
            dq.append(trade)

    async def get_last(self, symbol: str, limit: int = 6) -> List[Dict[str, Any]]:
        async with self._lock:
            dq = self._store.get(symbol, deque())
            if not dq:
                return []
            return list(dq)[-limit:][::-1]  # en yeniler önde


trade_hub = TradeHub()
