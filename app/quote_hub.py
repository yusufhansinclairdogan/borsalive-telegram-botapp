import asyncio
from typing import Dict, Any, Optional


class QuoteHub:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._q: Dict[str, Dict[str, Any]] = {}

    async def set(self, symbol: str, q: Dict[str, Any]) -> None:
        async with self._lock:
            self._q[symbol] = q

    async def get(self, symbol: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            return self._q.get(symbol)

    async def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return a shallow copy of the current quote map."""
        async with self._lock:
            return dict(self._q)


quote_hub = QuoteHub()
