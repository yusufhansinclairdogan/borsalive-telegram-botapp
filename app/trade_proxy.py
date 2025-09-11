# app/trade_proxy.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import base64
import logging
import random
import traceback
from typing import AsyncIterator, Optional, List

from websockets.client import connect
from websockets.exceptions import ConnectionClosed

from .config import settings
from .connect_builder import replace_jwt_in_connect
from .token_manager import TokenManager

log = logging.getLogger("trade_proxy")

# -------------------- low-level helpers --------------------


async def _send(ws, b: bytes, note: str = ""):
    """ws.send() sarmalayıcısı: kısa base64 log yazar."""
    try:
        await ws.send(b)
        try:
            b64 = base64.b64encode(b).decode()
        except Exception:
            b64 = "<bin>"
        log.info("WS→UP %-32s len=%-5d b64=%s", note, len(b), b64[:120])
    except Exception as e:
        log.error("send fail (%s): %s\n%s", note, e, traceback.format_exc())
        raise


def _read_vlq(buf: bytes, i: int) -> tuple[int, int]:
    """MQTT Remaining Length (VLQ) decode."""
    m = 1
    val = 0
    n = 0
    L = len(buf)
    while True:
        if i + n >= L:
            raise ValueError("VLQ out of range")
        b = buf[i + n]
        n += 1
        val += (b & 0x7F) * m
        if (b & 0x80) == 0:
            break
        m *= 128
        if m > (128**3):
            raise ValueError("VLQ too large")
    return val, n


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


def _looks_connack(b: bytes) -> bool:
    # 0x20 (CONNACK), rem.len >= 2, flags=0x00, rc=0x00
    return len(b) >= 4 and b[0] == 0x20 and b[1] >= 2 and b[2] == 0x00 and b[3] == 0x00


def _looks_suback(b: bytes) -> bool:
    return len(b) >= 4 and ((b[0] >> 4) & 0x0F) == 0x09  # SUBACK


def _iter_publish_payloads(ws_frame: bytes):
    """
    WS binary frame içinde birden fazla MQTT paketi olabilir.
    PUBLISH (0x3) paketlerinin (topic, payload) ikilisini yield eder.
    """
    i = 0
    data = ws_frame
    L = len(data)

    while i < L:
        if i + 2 > L:
            break

        fixed = data[i]
        i += 1

        # Remaining Length (VLQ)
        try:
            rem_len, n_vlq = _read_vlq(data, i)
        except Exception:
            return
        i += n_vlq

        if i + rem_len > L:
            break

        packet = data[i : i + rem_len]
        i += rem_len

        ptype = (fixed >> 4) & 0x0F
        flags = fixed & 0x0F
        if ptype != 0x03:  # PUBLISH değil
            continue

        j = 0
        if j + 2 > len(packet):
            continue
        tlen = int.from_bytes(packet[j : j + 2], "big")
        j += 2
        if j + tlen > len(packet):
            continue
        topic_b = packet[j : j + tlen]
        j += tlen

        qos = (flags >> 1) & 0x03
        if qos:
            if j + 2 > len(packet):
                continue
            _pid = int.from_bytes(packet[j : j + 2], "big")
            j += 2

        try:
            topic = topic_b.decode("utf-8", "ignore")
        except Exception:
            topic = ""

        payload = packet[j:]
        # Debug: gelen publish'i bir satırda görelim (kısaltılmış topic)
        log.debug("TRADE PUBLISH topic=%s len=%d", topic, len(payload))
        yield (topic, payload)


# Trade de aynı JWT’yi kullanıyoruz.
token_manager = TokenManager(initial_jwt=settings.INITIAL_JWT)

# -------------------- client --------------------


class MatrixTradeClient:
    """
    Her sembol için trade WS bağlantısı kurar; PUBLISH payload'larını stream eder.
    CONNECT template içine JWT dinamik gömülür.
    SUBSCRIBE gövdesi aynı anda birden fazla olası topic’e abone olacak şekilde hazırlanır.
    """

    def __init__(self, symbol: str, connect_template_b64: Optional[str] = None):
        self.symbol = symbol.upper()

        self.url = (
            getattr(settings, "MATRIX_TRADE_URL", None)
            or "wss://rtstream.radix.matriksdata.com/trade"
        )
        self.origin = settings.MATRIX_ORIGIN
        self.subprotocol = settings.MATRIX_SUBPROTOCOL

        # Öncelik: parametre > .env TRADE_CONNECT_TEMPLATE_B64 > .env CONNECT_TEMPLATE_B64
        tmpl_b64 = (
            connect_template_b64
            or getattr(settings, "TRADE_CONNECT_TEMPLATE_B64", "")
            or settings.CONNECT_TEMPLATE_B64
        )
        self.connect_template: Optional[bytes] = (
            base64.b64decode(tmpl_b64) if tmpl_b64 else None
        )

        # Debug amaçlı saklayalım
        self.subscribe_body: Optional[bytes] = None

        # Olası topic varyantlarını sırayla deneyeceğiz (tek SUBSCRIBE içinde hepsine abone olur)
        # İstersen .env’de MATRIX_TRADE_TOPIC_CANDIDATES ile override edebilirsin (virgülle ayrılmış formatlar).
        self.topic_candidates: List[str] = self._build_topic_candidates()

    def _build_topic_candidates(self) -> List[str]:
        env_fmt = getattr(settings, "MATRIX_TRADE_TOPIC_CANDIDATES", "") or ""
        if env_fmt:
            # örn: "mx/trade/{sym}@lvl2,mx/trade/{sym},mx/trades/{sym}@lvl2"
            fmts = [s.strip() for s in env_fmt.split(",") if s.strip()]
            return [
                f.replace("{sym}", self.symbol).replace("{symbol}", self.symbol)
                for f in fmts
            ]

        # Varsayılan deneme seti (en yaygın varyantlar)
        return [
            f"mx/trade/{self.symbol}@lvl2",
            # f"mx/trade/{self.symbol}",
            # f"mx/trades/{self.symbol}@lvl2",
            # f"mx/trades/{self.symbol}",
        ]

    async def connect_and_stream(self) -> AsyncIterator[bytes]:
        headers = {
            "Origin": self.origin,
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0",
        }
        subprotocols = [self.subprotocol] if self.subprotocol else None

        async with connect(
            self.url,
            extra_headers=headers,
            subprotocols=subprotocols,
            ping_interval=25,
            ping_timeout=15,
            close_timeout=10,
            max_queue=None,
        ) as ws:
            log.info("Connected to Matriks trade WS for %s", self.symbol)

            # 1) EA== (0x10 preamble)
            await _send(ws, b"\x10", "EA== preamble (trade)")
            await asyncio.sleep(0.02)

            # 2) CONNECT (template + JWT)
            if not self.connect_template:
                raise RuntimeError(
                    "CONNECT template yok (TRADE_CONNECT_TEMPLATE_B64/CONNECT_TEMPLATE_B64)."
                )

            jwt = token_manager.get()
            if not jwt:
                raise RuntimeError("JWT yok/expired. /admin/jwt ile güncelle.")

            connect_packet = replace_jwt_in_connect(self.connect_template, jwt.encode())
            await _send(ws, connect_packet, "CONNECT (trade)")
            await asyncio.sleep(0.02)

            # 3) CONNACK bekle
            got_connack = False
            for _ in range(20):  # ~10s
                try:
                    fr = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if isinstance(fr, (bytes, bytearray)):
                    if _looks_connack(fr):
                        log.info("TRADE: CONNACK ok")
                        got_connack = True
                        break
                    if _looks_suback(fr):
                        log.info("TRADE: early SUBACK (len=%d)", len(fr))
                # text frame yoksay
            if not got_connack:
                log.warning("TRADE: CONNACK alınamadı; devam ediliyor.")

            await asyncio.sleep(0.02)

            # 4) SUBSCRIBE header gg== (0x82)
            await _send(ws, b"\x82", "SUBSCRIBE header gg== (trade)")
            await asyncio.sleep(0.02)

            # 5) SUBSCRIBE body (çoklu topic)
            pid = random.randint(0x2000, 0x7FFF)
            payload = bytearray()
            for top in self.topic_candidates:
                tb = top.encode("utf-8")
                payload += len(tb).to_bytes(2, "big") + tb + b"\x00"  # qos=0

            body = pid.to_bytes(2, "big") + bytes(payload)
            rl = _enc_vlq(len(body))
            sub_body = rl + body
            self.subscribe_body = sub_body
            await _send(ws, sub_body, "SUBSCRIBE body (trade, multi-topic)")

            # 5b) SUBACK bekle ve bu arada publish kaçmasın
            got_suback = False
            for _ in range(20):  # ~10s
                try:
                    fr = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if isinstance(fr, (bytes, bytearray)):
                    if _looks_suback(fr):
                        log.info("TRADE: SUBACK ok")
                        got_suback = True
                        break
                    # publish geldiyse kaçırmayalım
                    for topic, payload in _iter_publish_payloads(fr):
                        # Topic’i bir kere daha kontrol etmeye gerek yok (zaten publish)
                        # Frontend base64 istiyor -> sadece payload’ı üst katmana veriyoruz
                        yield payload
            if not got_suback:
                log.warning("TRADE: SUBACK alınamadı; yine de devam ediliyor.")

            # 6) heartbeat (PINGREQ): wAA= (0xC0 0x00)
            heartbeat = base64.b64decode("wAA=")

            async def _hb():
                while True:
                    try:
                        await _send(ws, heartbeat, "heartbeat wAA= (trade)")
                    except Exception:
                        break
                    await asyncio.sleep(55)

            hb_task = asyncio.create_task(_hb())

            try:
                async for raw in ws:
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    for topic, payload in _iter_publish_payloads(raw):
                        # publish geldi — debug’ı _iter_publish_payloads yazdı
                        yield payload
            except ConnectionClosed:
                pass
            finally:
                hb_task.cancel()
