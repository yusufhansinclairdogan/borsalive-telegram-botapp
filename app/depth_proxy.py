# app/depth_proxy.py
# -*- coding: utf-8 -*-
"""
Matriks depth WS istemcisi.
Sıra:
  1) EA==                 -> 0x10 (preamble)
  2) CONNECT (template+JWT ile dinamik)
  3) CONNACK bekle (IAIAAA==)
  4) gg==                 -> 0x82 (SUBSCRIBE başlık frame)
  5) SUBSCRIBE gövdesi    -> 3 konu: lvl2, lvl3, depthstats (tek frame, chunked)
  6) heartbeat wAA=       -> periyodik (60s)
  7) PUBLISH payload'larını decode et
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import traceback
from typing import AsyncIterator, List, Optional

from websockets.client import connect

from .config import settings
from .connect_builder import replace_jwt_in_connect
from .token_manager import TokenManager
from .mqtt_subscribe_chunked import build_chunked_subscribe
from .depth_parser import decode_depth_snapshot

log = logging.getLogger("depth_proxy")

# ---------------------------------------------------------------------------
# MQTT yardımcıları
# ---------------------------------------------------------------------------

def mqtt_iter_publish_payloads(ws_frame: bytes):
    """
    Tek WS binary frame içinde birden fazla MQTT paketi olabilir.
    Bu fonksiyon PUBLISH (0x3) paketlerinin payload'larını yield eder.
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
        mult = 1
        rem_len = 0
        while True:
            if i >= L:
                return
            enc = data[i]
            i += 1
            rem_len += (enc & 127) * mult
            if enc & 128 == 0:
                break
            mult *= 128

        if i + rem_len > L:
            break

        packet = data[i : i + rem_len]
        i += rem_len

        ptype = (fixed >> 4) & 0x0F  # üst 4 bit
        flags = fixed & 0x0F

        if ptype != 0x03:  # PUBLISH değil
            continue

        # PUBLISH formatı:
        # [0..1] Topic length (u16 BE)
        # [2..]  Topic string
        # [..]   (QoS>0 ise PacketId u16)
        # [..]   Payload
        j = 0
        if j + 2 > len(packet):
            continue
        tlen = int.from_bytes(packet[j : j + 2], "big")
        j += 2
        if j + tlen > len(packet):
            continue
        topic = packet[j : j + tlen]
        j += tlen

        qos = (flags >> 1) & 0x03
        if qos:
            if j + 2 > len(packet):
                continue
            _pid = int.from_bytes(packet[j : j + 2], "big")
            j += 2

        payload = packet[j:]

        try:
            t = topic.decode("utf-8", "ignore")
        except Exception:
            t = ""
        if t.startswith("mx/depth/") or t.startswith("mx/depthstats/"):
            yield payload


# ---------------------------------------------------------------------------
# CONNECT / JWT ve çerçeve tanıma
# ---------------------------------------------------------------------------

token_manager = TokenManager(initial_jwt=settings.INITIAL_JWT)

def _looks_connack(b: bytes) -> bool:
    # 0x20 (CONNACK), rem.len >= 2, flags=0x00, rc=0x00
    return len(b) >= 4 and b[0] == 0x20 and b[1] >= 2 and b[2] == 0x00 and b[3] == 0x00

def _looks_suback(b: bytes) -> bool:
    # SUBACK -> type 0x09
    return len(b) >= 4 and ((b[0] >> 4) & 0x0F) == 0x09

async def _send(ws, b: bytes, note: str = ""):
    """
    ws.send() için sarmalayıcı: gönderdiğini base64 kısa loglar.
    """
    try:
        await ws.send(b)
        try:
            b64 = base64.b64encode(b).decode()
        except Exception:
            b64 = "<bin>"
        log.info("WS→UP %-24s len=%-5d b64=%s", note, len(b), b64[:120])
    except Exception as e:
        log.error("send fail (%s): %s\n%s", note, e, traceback.format_exc())
        raise


# ---------------------------------------------------------------------------
# İstemci
# ---------------------------------------------------------------------------

class MatrixDepthClient:
    """
    Her sembol için upstream WS bağlantısı kurar;
    decode ettiği seviyeleri (list[dict]) olarak stream eder.
    """

    def __init__(
        self,
        symbol: str,
        connect_template_b64: Optional[str] = None,
        # Geriye uyumluluk parametreleri (kullanmasak da kabul ediyoruz):
        fallback_frames_b64: Optional[List[str]] = None,
        subscribe_frame_b64: Optional[str] = None,
    ):
        self.symbol = symbol.upper()

        # WS metas
        self.url = settings.MATRIX_DEPTH_URL
        self.origin = settings.MATRIX_ORIGIN
        self.subprotocol = settings.MATRIX_SUBPROTOCOL

        # CONNECT template (JWT bunun içine enjekte edilir)
        self.connect_template: Optional[bytes] = (
            base64.b64decode(connect_template_b64) if connect_template_b64 else None
        )

        # İsteğe bağlı ham SUBSCRIBE gövdesi (özel/test)
        self.subscribe_frame: Optional[bytes] = (
            base64.b64decode(subscribe_frame_b64) if subscribe_frame_b64 else None
        )

    def _topics(self) -> List[str]:
        return [
            f"mx/depth/{self.symbol}@lvl2",
            # f"mx/depth/{self.symbol}@lvl3",
            # f"mx/depthstats/{self.symbol}",
        ]

    async def connect_and_stream(self) -> AsyncIterator[List[dict]]:
        """
        Upstream'e bağlanır, doğru sırayla frame'leri yollar; payload'ları decode edip yield eder.
        """
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
            ping_interval=30,
            ping_timeout=20,
            close_timeout=10,
            max_queue=None,
        ) as ws:
            log.info("Connected to Matriks depth WS for %s", self.symbol)

            # (1) EA== (0x10)
            await _send(ws, b"\x10", "EA== preamble")
            await asyncio.sleep(0.02)

            # (2) CONNECT (template + JWT)
            if not self.connect_template:
                raise RuntimeError("CONNECT template yok (CONNECT_TEMPLATE_B64).")
            jwt = token_manager.get()
            if not jwt:
                raise RuntimeError("JWT yok/expired. /admin/jwt ile güncelle.")
            connect_packet = replace_jwt_in_connect(self.connect_template, jwt.encode())
            await _send(ws, connect_packet, "CONNECT (template+JWT)")

            # (3) CONNACK bekle (kısa pencere); diğer paketleri de işleyelim
            got_connack = False
            for _ in range(12):  # ~6s
                try:
                    fr = await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if isinstance(fr, (bytes, bytearray)):
                    if _looks_connack(fr):
                        log.info("UP→WS CONNACK ok (len=%d)", len(fr))
                        got_connack = True
                        break
                    if _looks_suback(fr):
                        log.info("UP→WS SUBACK (len=%d)", len(fr))
                        continue
                    # Erken PUBLISH geldiyse decode et
                    for payload in mqtt_iter_publish_payloads(fr):
                        try:
                            levels = decode_depth_snapshot(payload)
                        except Exception:
                            continue
                        if levels:
                            yield levels
                # text frame gelirse yoksay

            if not got_connack:
                log.warning("CONNACK alınamadı; devam ediliyor.")

            await asyncio.sleep(0.02)

            # (4) SUBSCRIBE başlığı: gg== (0x82)
            await _send(ws, b"\x82", "SUBSCRIBE header gg==")
            await asyncio.sleep(0.02)

            # (5) SUBSCRIBE gövdesi (chunked, 3 konu)
            if self.subscribe_frame:
                await _send(ws, self.subscribe_frame, "SUBSCRIBE custom body")
            else:
                topics = self._topics()
                base_pid = random.randint(0x2000, 0x7FFF)  # ardışık 3 pid
                sub_chunk = build_chunked_subscribe(topics, base_pid)
                await _send(ws, sub_chunk, "SUBSCRIBE chunked body")

            await asyncio.sleep(0.02)

            # (6) Heartbeat: wAA= (0xC0 0x00) periyodik
            heartbeat = base64.b64decode("wAA=")

            async def _hb():
                while True:
                    try:
                        await _send(ws, heartbeat, "heartbeat wAA=")
                    except Exception:
                        break
                    await asyncio.sleep(60)

            hb_task = asyncio.create_task(_hb())

            try:
                async for raw in ws:
                    if isinstance(raw, (bytes, bytearray)):
                        # SUBACK'leri kısa logla
                        if _looks_suback(raw):
                            log.info("UP→WS SUBACK (len=%d)", len(raw))
                            continue
                        # PUBLISH payloadlarını çıkar
                        any_level = False
                        for payload in mqtt_iter_publish_payloads(raw):
                            try:
                                levels = decode_depth_snapshot(payload)
                            except Exception:
                                continue
                            if levels:
                                any_level = True
                                yield levels
                        if not any_level:
                            # debug amaçlı ilk 1-2 paket kısa log
                            try:
                                b64 = base64.b64encode(raw).decode()
                            except Exception:
                                b64 = "<bin>"
                            log.debug("UP→WS non-publish len=%d b0=0x%02x b64=%s",
                                      len(raw), raw[0] if raw else -1, b64[:120])
                    # text frame -> yoksay
            finally:
                hb_task.cancel()
