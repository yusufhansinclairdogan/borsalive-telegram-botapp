# app/market_proxy.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio, base64, logging, random
from typing import AsyncIterator, Optional

from websockets.client import connect
from websockets.exceptions import ConnectionClosed

from .config import settings
from .connect_builder import replace_jwt_in_connect
from .token_manager import TokenManager

log = logging.getLogger("market_proxy")
token_manager = TokenManager(initial_jwt=settings.INITIAL_JWT)

def _looks_connack(b: bytes) -> bool:
    return len(b) >= 4 and b[0] == 0x20 and b[1] >= 2 and b[2] == 0x00 and b[3] == 0x00

def _looks_suback(b: bytes) -> bool:
    return len(b) >= 4 and ((b[0] >> 4) & 0x0F) == 0x09

async def _send(ws, b: bytes, note: str = ""):
    await ws.send(b)
    try:
        b64 = base64.b64encode(b).decode()
    except Exception:
        b64 = "<bin>"
    log.info("WS→UP %-28s len=%-5d b64=%s", note, len(b), b64[:120])

def _enc_vlq(n: int) -> bytes:
    out = bytearray()
    while True:
        d = n % 128
        n //= 128
        if n:
            d |= 0x80
        out.append(d)
        if not n:
            break
    return bytes(out)

def _iter_publish_payloads(ws_frame: bytes):
    """WS binary frame içinde MQTT PUBLISH paketlerinin payload’larını yield eder."""
    i = 0; data = ws_frame; L = len(data)
    while i < L:
        if i + 2 > L: break
        fixed = data[i]; i += 1
        # remaining length (VLQ)
        m=1; rem=0; n=0
        while True:
            if i+n >= L: return
            b = data[i+n]; n += 1
            rem += (b & 0x7F) * m
            if (b & 0x80) == 0: break
            m *= 128
            if m > (128**3): return
        i += n
        if i + rem > L: break
        packet = data[i:i+rem]; i += rem

        ptype = (fixed >> 4) & 0x0F
        flags = fixed & 0x0F
        if ptype != 0x03:  # PUBLISH değil
            continue

        j = 0
        if j + 2 > len(packet): continue
        tlen = int.from_bytes(packet[j:j+2], "big"); j += 2
        if j + tlen > len(packet): continue
        # topic = packet[j:j+tlen]  # gerekirse decode edebilirsin
        j += tlen

        qos = (flags >> 1) & 0x03
        if qos:
            if j + 2 > len(packet): continue
            _pid = int.from_bytes(packet[j:j+2], "big"); j += 2

        payload = packet[j:]
        yield payload

def _build_sub_body(symbol: str, pid: int) -> bytes:
    """MQTT SUBSCRIBE body: PID(2) + [len(2)+topic+qos]"""
    topic = f"mx/symbol/{symbol}@lvl2".encode("ascii")
    tb = len(topic).to_bytes(2, "big") + topic + b"\x00"  # qos=0
    return pid.to_bytes(2, "big") + tb

class MatrixMarketClient:
    def __init__(self, symbol: str, connect_template_b64: Optional[str] = None):
        self.symbol = symbol.upper()
        self.url = "wss://rtstream.radix.matriksdata.com/market"
        self.origin = settings.MATRIX_ORIGIN
        self.subprotocol = settings.MATRIX_SUBPROTOCOL
        tmpl_b64 = connect_template_b64 or getattr(settings, "MARKET_CONNECT_TEMPLATE_B64", "") or settings.CONNECT_TEMPLATE_B64
        if not tmpl_b64:
            raise RuntimeError("Market CONNECT template (MARKET_CONNECT_TEMPLATE_B64/CONNECT_TEMPLATE_B64) yok.")
        self.connect_template = base64.b64decode(tmpl_b64)

    async def connect_and_stream(self) -> AsyncIterator[bytes]:
        headers = {"Origin": self.origin, "Pragma":"no-cache", "Cache-Control":"no-cache", "User-Agent":"Mozilla/5.0"}
        subprotocols = [self.subprotocol] if self.subprotocol else None

        async with connect(self.url, extra_headers=headers, subprotocols=subprotocols,
                           ping_interval=25, ping_timeout=15, close_timeout=10, max_queue=None) as ws:
            log.info("Connected to MATRİKS MARKET WS for %s", self.symbol)

            # 1) preamble
            await _send(ws, b"\x10", "EA== preamble (market)")
            await asyncio.sleep(0.02)

            # 2) CONNECT + JWT
            jwt = token_manager.get()
            if not jwt:
                raise RuntimeError("JWT yok/expired. /admin/jwt ile güncelle.")
            connect_packet = replace_jwt_in_connect(self.connect_template, jwt.encode())
            await _send(ws, connect_packet, "CONNECT (market)")

            # 3) CONNACK / erken yayın
            got_connack = False
            for _ in range(20):
                try:
                    fr = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if isinstance(fr, (bytes, bytearray)):
                    if _looks_connack(fr):
                        log.info("MARKET: CONNACK ok")
                        got_connack = True
                        break
                    if _looks_suback(fr):
                        log.info("MARKET: early SUBACK len=%d", len(fr))
                        continue
                    for payload in _iter_publish_payloads(fr):
                        yield payload
            if not got_connack:
                log.warning("MARKET: CONNACK alınamadı; devam.")

            # 4) SUBSCRIBE (standart MQTT)
            await _send(ws, b"\x82", "SUBSCRIBE header (market)")
            pid = random.randint(0x2000, 0x7FFF)
            body = _build_sub_body(self.symbol, pid)
            rl = _enc_vlq(len(body))
            await _send(ws, rl + body, "SUBSCRIBE body (market)")

            # 5) heartbeat
            heartbeat = base64.b64decode("wAA=")
            async def _hb():
                while True:
                    try:
                        await _send(ws, heartbeat, "heartbeat (market)")
                    except Exception:
                        break
                    await asyncio.sleep(55)
            hb_task = asyncio.create_task(_hb())

            try:
                async for raw in ws:
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    if _looks_suback(raw):
                        log.info("MARKET: SUBACK ok")
                        continue
                    for payload in _iter_publish_payloads(raw):
                        yield payload
            except ConnectionClosed:
                pass
            finally:
                hb_task.cancel()
