# app/auto_jwt_refresher.py
from __future__ import annotations
import asyncio, logging, time
from typing import Optional
from .token_manager import TokenManager
from .matriks_autoauth import fetch_jwt_via_browser
from .config import settings

log = logging.getLogger("autoauth")

class AutoJWTRefresher:
    def __init__(self, tm: TokenManager):
        self.tm = tm
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():  # zaten çalışıyor
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._runner())

    async def stop(self) -> None:
        if self._task:
            self._stop.set()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except Exception:
                pass

    async def _runner(self):
        interval = max(120, settings.JWT_REFRESH_INTERVAL_SEC)
        while not self._stop.is_set():
            try:
                # Token yoksa ya da bitmesine az kaldıysa token_manager.get() None döner.
                if self.tm.get() is None:
                    log.info("Otomatik JWT yenileme başlıyor…")
                    token = await fetch_jwt_via_browser()
                    if token:
                        self.tm.set(token)
                        log.info("JWT yenilendi (exp=%s)", self.tm.info().get("exp"))
                    else:
                        log.warning("JWT alınamadı.")
                # sıradaki kontrol
            except Exception:
                log.exception("AutoJWTRefresher döngü hatası")
            await asyncio.wait([self._stop.wait()], timeout=interval)
