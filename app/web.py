# app/web.py
from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Response,
    Header,
    HTTPException,
    Query,
)
import gzip
from typing import Optional, Dict, Any, List, Set
import asyncio
import base64
import struct
import time
import math
from .market_proxy import MatrixMarketClient, MatrixMarketHeatmapClient
from .quote_hub import quote_hub
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_204_NO_CONTENT
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState
from .market_proxy import MatrixMarketClient
import asyncio
import base64
import json
import logging
import time
import httpx
import struct
from starlette.websockets import WebSocketDisconnect
from .config import settings
from .depth_hub import hub
from .snapshot import render_depth_png
from .depth_proxy import MatrixDepthClient, token_manager
from .trade_proxy import MatrixTradeClient
import struct, asyncio
from .market_proxy import MatrixMarketClient
from .trade_proxy import MatrixTradeClient
from .depth_hub import hub as depth_hub
from .trade_hub import trade_hub
from fastapi import Body
from typing import Optional
from starlette.responses import JSONResponse
from .config import settings
import urllib.parse

# app/routers/symbols.py
from fastapi import APIRouter, Response, Query
import httpx, json, time, logging
from typing import Optional
from app.config import settings
from app.depth_proxy import token_manager  # TokenManager (get() mevcut)
from app.routers import symbols as symbols_router


router = APIRouter()
router.include_router(symbols_router.router)
# Basit cache (mid’e göre). TTL kısa tutuyoruz.
_CACHE = {}
_TTL = 60.0


def _headers(jwt_token: str) -> dict:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"jwt {jwt_token}",
        "Origin": settings.MATRIX_ORIGIN or "https://app.matrikswebtrader.com",
        "Referer": "https://app.matrikswebtrader.com/",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


_NEWS_QID_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_QID_TTL = 45.0


def _normalize_jwt_header(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    low = raw.lower()
    if low.startswith("bearer ") or low.startswith("jwt "):
        return raw
    return f"jwt {raw}"


def _news_headers(auth_header: str) -> Dict[str, str]:
    origin = settings.MATRIX_ORIGIN or "https://app.matrikswebtrader.com"
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": auth_header,
        "Origin": origin,
        "Referer": "https://app.matrikswebtrader.com/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    }


def _merge_filter_value(target: Dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    existing = target.get(key)
    if existing is None:
        target[key] = value
    elif isinstance(existing, list):
        if isinstance(value, list):
            existing.extend(v for v in value if v not in existing)
        else:
            if value not in existing:
                existing.append(value)
    else:
        if isinstance(value, list):
            values = [existing]
            values.extend(v for v in value if v not in values)
            target[key] = values
        elif value != existing:
            target[key] = [existing, value]


def _cleanup_filters(data: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list):
            reduced = [v for v in value if v not in (None, "")]
            if reduced:
                cleaned[key] = reduced
        elif value not in (None, ""):
            cleaned[key] = value
    return cleaned


def _freeze_for_cache(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _freeze_for_cache(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_freeze_for_cache(v) for v in value]
    return value


def _news_cache_key(content: str, filters_signature: Dict[str, Any]) -> str:
    frozen = _freeze_for_cache(filters_signature)
    return json.dumps(
        {"content": content, "filters": frozen}, sort_keys=True, ensure_ascii=False
    )


def _parse_upstream_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except json.JSONDecodeError:
        try:
            return json.loads(gzip.decompress(resp.content).decode("utf-8"))
        except Exception:
            raise


def _extract_qid(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        qid = payload.get("qid")
        if isinstance(qid, str) and qid:
            return qid
        for key in ("data", "result", "response"):
            sub = payload.get(key)
            sub_qid = _extract_qid(sub)
            if sub_qid:
                return sub_qid
    return None


def _extract_filters(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("filter", "filters"):
            val = payload.get(key)
            if isinstance(val, dict):
                return val
        for key in ("data", "result", "response"):
            sub = payload.get(key)
            extracted = _extract_filters(sub)
            if extracted:
                return extracted
    return None


def _extract_items(payload: Any) -> List[Any]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
        for key in ("data", "result", "response"):
            sub = payload.get(key)
            nested = _extract_items(sub)
            if nested:
                return nested
    return []


def _extract_pagination_meta(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        for key in ("pagination", "page", "meta", "page_info"):
            meta = payload.get(key)
            if isinstance(meta, dict):
                return meta
        for key in ("data", "result", "response"):
            sub = payload.get(key)
            meta = _extract_pagination_meta(sub)
            if meta:
                return meta
    return {}


def _first_numeric(keys: List[str], *sources: Dict[str, Any]) -> Optional[int]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key not in source:
                continue
            val = source.get(key)
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, str):
                txt = val.strip()
                if not txt:
                    continue
                try:
                    return int(float(txt))
                except ValueError:
                    continue
    return None


@router.get("/api/sectoral-brief")
async def sectoral_brief(
    mid: Optional[str] = Query(None),
    ngsw_bypass: Optional[bool] = Query(True, alias="ngsw-bypass"),
):
    """
    Matriks sectoral-brief proxy.
    - JWT: token_manager.get() + INITIAL_JWT fallback
    - URL: mid paramını upstream’e geçirir; yoksa epoch ms üretir.
    - 200 değilse 502/504 döner; 500 yerine log’la birlikte kontrollü hata.
    """

    # mid yoksa üret (epoch ms)
    if not mid:
        mid = str(int(time.time() * 1000))

    # cache anahtarı
    ck = f"{mid}"
    now = time.time()
    ent = _CACHE.get(ck)
    if ent and (now - ent["t"] < _TTL):
        return ent["data"]

    # JWT al (TokenManager.get()) + INITIAL_JWT fallback
    jwt_token = None
    try:
        jwt_token = token_manager.get()
    except Exception:
        logging.exception("sectoral-brief: token_manager.get() hata")
    if not jwt_token:
        jwt_token = settings.INITIAL_JWT or ""
    if not jwt_token:
        logging.error("sectoral-brief: JWT alınamadı")
        return Response(
            content=json.dumps({"error": "jwt_unavailable"}),
            status_code=502,
            media_type="application/json",
        )

    # Upstream URL (mid + ngsw-bypass=true)
    upstream_url = f"https://api.matriksdata.com/dumrul/v1/sectoral-brief?mid={mid}&ngsw-bypass=true"

    # Upstream’e istek
    try:
        async with httpx.AsyncClient(timeout=8.0) as cli:
            r = await cli.get(upstream_url, headers=_headers(jwt_token))
        if r.status_code != 200:
            logging.error("sectoral-brief upstream %s: %s", r.status_code, r.text[:300])
            return Response(
                content=json.dumps(
                    {"error": "upstream_non_200", "status": r.status_code}
                ),
                status_code=502,
                media_type="application/json",
            )
        data = r.json()
        if not isinstance(data, list):
            logging.error("sectoral-brief bad payload: %s", str(data)[:300])
            return Response(
                content=json.dumps({"error": "bad_payload"}),
                status_code=502,
                media_type="application/json",
            )
        _CACHE[ck] = {"t": now, "data": data}
        return data

    except httpx.TimeoutException:
        logging.exception("sectoral-brief timeout")
        return Response(
            content=json.dumps({"error": "timeout"}),
            status_code=504,
            media_type="application/json",
        )
    except Exception:
        logging.exception("sectoral-brief unknown error")
        return Response(
            content=json.dumps({"error": "proxy_failed"}),
            status_code=502,
            media_type="application/json",
        )


log = logging.getLogger("app.web")
templates = Jinja2Templates(directory="app/templates")
app = FastAPI(title="borsalive-api")

MATRIX_LOGO_URL = "https://api.matriksdata.com/dumrul/v1/mtx-cdn"

# --- CORS ---
ALLOWED_ORIGINS = [
    settings.WEBAPP_BASE,
    "https://web.telegram.org",
    "https://web.telegram.org/a",
    "https://web.telegram.org/k",
    "https://t.me",
    "https://telegram.org",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "https://localhost:8000",
    "https://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static & templates ---
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# --- Utils ---
async def _safe_send(ws: WebSocket, obj) -> bool:
    if ws.application_state != WebSocketState.CONNECTED:
        return False
    try:
        await ws.send_json(obj)
        return True
    except WebSocketDisconnect:
        return False
    except RuntimeError as e:
        log.warning("Client closed while sending: %s", e)
        return False
    except Exception:
        log.exception("send_json failed")
        return False


HEATMAP_SYMBOLS = tuple(settings.HEATMAP_SYMBOLS)
HEATMAP_SYMBOL_SET = {s.upper() for s in HEATMAP_SYMBOLS}
_HEATMAP_BATCH_SIZE = 20
_heatmap_clients: Set[WebSocket] = set()
_heatmap_clients_lock = asyncio.Lock()
_heatmap_task_lock = asyncio.Lock()
_heatmap_dirty = asyncio.Event()
_heatmap_stream_task: Optional[asyncio.Task] = None
_heatmap_broadcast_task: Optional[asyncio.Task] = None

if len(HEATMAP_SYMBOLS) != 60:
    log.warning("[HEATMAP]: expected 60 symbols, got %d", len(HEATMAP_SYMBOLS))


def _extract_symbol_from_topic(topic: str) -> Optional[str]:
    if not topic:
        return None
    try:
        tail = topic.split("/", 2)[-1]
    except Exception:
        return None
    if "@" in tail:
        tail = tail.split("@", 1)[0]
    sym = tail.strip().upper()
    return sym or None


def _build_heatmap_batches(quotes: List[Dict[str, Any]], ts_ms: int):
    if not quotes:
        return
    batch_size = _HEATMAP_BATCH_SIZE
    total = max(1, math.ceil(len(quotes) / batch_size))
    for idx in range(total):
        sl = quotes[idx * batch_size : (idx + 1) * batch_size]
        yield {
            "type": "batch",
            "index": idx,
            "total": total,
            "ts": ts_ms,
            "quotes": sl,
        }


async def _heatmap_collect_quotes() -> List[Dict[str, Any]]:
    snap = await quote_hub.snapshot()
    out: List[Dict[str, Any]] = []
    for sym in HEATMAP_SYMBOLS:
        q = snap.get(sym)
        if not q:
            continue
        out.append(
            {
                "symbol": sym,
                "last": q.get("last"),
                "prev_close": q.get("prev_close"),
                "change_pct": q.get("change_pct"),
                "updated_at": q.get("updated_at"),
            }
        )
    return out


async def _broadcast_heatmap_message(message: Dict[str, Any]) -> None:
    async with _heatmap_clients_lock:
        targets = list(_heatmap_clients)
    if not targets:
        return
    stale: List[WebSocket] = []
    for ws in targets:
        try:
            await ws.send_json(message)
        except WebSocketDisconnect:
            stale.append(ws)
        except RuntimeError:
            stale.append(ws)
        except Exception:
            log.exception("[HEATMAP]: send_json failed")
            stale.append(ws)
    if stale:
        async with _heatmap_clients_lock:
            for ws in stale:
                _heatmap_clients.discard(ws)


@app.get("/webapp/news", response_class=HTMLResponse)
def news_webapp(request: Request, symbol: str = "ASELS"):
    sym = (symbol or "ASELS").upper()
    return templates.TemplateResponse(
        "news.html",
        {
            "request": request,
            "symbol": sym,
            "api_base": settings.API_BASE.rstrip("/"),
            "webapp_base": settings.WEBAPP_BASE.rstrip("/"),
        },
    )


@app.get("/webapp/heatmap", response_class=HTMLResponse)
def heatmap_webapp(request: Request, symbol: str = "ASELS"):
    sym = (symbol or "ASELS").upper()
    return templates.TemplateResponse(
        "heatmap.html",
        {
            "request": request,
            "symbol": sym,
            "websocket_url": "/ws/heatmap",
        },
    )


async def _heatmap_broadcast_loop():
    try:
        while True:
            await _heatmap_dirty.wait()
            _heatmap_dirty.clear()
            await asyncio.sleep(0.2)
            quotes = await _heatmap_collect_quotes()
            if not quotes:
                continue
            ts_ms = int(time.time() * 1000)
            for payload in _build_heatmap_batches(quotes, ts_ms):
                await _broadcast_heatmap_message(payload)
    except asyncio.CancelledError:
        pass


async def _heatmap_stream_loop():
    if not HEATMAP_SYMBOLS:
        log.warning("[HEATMAP]: no symbols configured; stream loop exiting")
        return
    client = MatrixMarketHeatmapClient(symbols=HEATMAP_SYMBOLS)
    try:
        async for topic, payload in client.connect_and_stream():
            sym = _extract_symbol_from_topic(topic)
            if not sym or sym not in HEATMAP_SYMBOL_SET:
                continue
            decoded = _decode_market_payload(payload)
            if not decoded:
                continue
            existing = await quote_hub.get(sym) or {}
            merged = dict(existing)
            merged["symbol"] = sym

            last_old = existing.get("last") if existing else None
            prev_old = existing.get("prev_close") if existing else None
            prev_change_pct = existing.get("change_pct") if existing else None

            last_val = decoded.get("last")
            last_changed = False
            if last_val is not None:
                last_changed = last_val != last_old
                merged["last"] = last_val

            prev_val = decoded.get("prev_close")
            prev_changed = False
            if prev_val is not None:
                prev_changed = prev_val != prev_old
                merged["prev_close"] = prev_val

            for key, value in decoded.items():
                if key in {"last", "prev_close", "change_pct"}:
                    continue
                if value is not None:
                    merged[key] = value

            merged_last = merged.get("last")
            merged_prev = merged.get("prev_close")

            if last_changed or prev_changed:
                if merged_last is not None and merged_prev not in (None, 0):
                    merged["change_pct"] = (
                        (merged_last - merged_prev) / merged_prev * 100.0
                    )
                else:
                    if prev_change_pct is not None:
                        merged["change_pct"] = prev_change_pct
                    else:
                        merged.pop("change_pct", None)
            else:
                new_change = decoded.get("change_pct")
                if new_change is not None:
                    merged["change_pct"] = new_change
                elif prev_change_pct is not None:
                    merged["change_pct"] = prev_change_pct
                else:
                    merged.pop("change_pct", None)

            merged["updated_at"] = int(time.time() * 1000)

            await quote_hub.set(sym, merged)
            _heatmap_dirty.set()
    except asyncio.CancelledError:
        raise


async def _ensure_heatmap_tasks() -> None:
    global _heatmap_stream_task, _heatmap_broadcast_task
    async with _heatmap_task_lock:
        if _heatmap_stream_task is None or _heatmap_stream_task.done():
            _heatmap_stream_task = asyncio.create_task(_heatmap_stream_loop())
        if _heatmap_broadcast_task is None or _heatmap_broadcast_task.done():
            _heatmap_broadcast_task = asyncio.create_task(_heatmap_broadcast_loop())


async def _heatmap_send_snapshot(ws: WebSocket) -> None:
    quotes = await _heatmap_collect_quotes()
    if not quotes:
        return
    ts_ms = int(time.time() * 1000)
    for payload in _build_heatmap_batches(quotes, ts_ms):
        await ws.send_json(payload)


# ---- minimal protobuf-like decoder for Trade ----
# fields: 1=symbol(str), 2=trade_id(str), 3=price(f32), 4=qty(varint),
#         5=side(str),   6=ts(varint),    7=buyer(str),  8=seller(str)
def _read_varint(buf: bytes, i: int):
    x = 0
    s = 0
    while True:
        b = buf[i]
        i += 1
        x |= (b & 0x7F) << s
        if not (b & 0x80):
            break
        s += 7
    return x, i


def _read_len_delim(buf: bytes, i: int):
    ln, i = _read_varint(buf, i)
    j = i + ln
    return buf[i:j], j


def _read_f32_le(buf: bytes, i: int):
    v = struct.unpack_from("<f", buf, i)[0]
    return float(v), i + 4


def _decode_trade_payload(u8: bytes) -> dict:
    out = {}
    i = 0
    L = len(u8)
    while i < L:
        tag, i = _read_varint(u8, i)
        field_no = tag >> 3
        wt = tag & 7
        if wt == 0:  # varint
            v, i = _read_varint(u8, i)
            if field_no == 4:
                out["qty"] = v
            elif field_no == 6:
                out["ts"] = v
        elif wt == 2:  # len-delimited (strings)
            s, i = _read_len_delim(u8, i)
            try:
                val = s.decode("utf-8")
            except Exception:
                val = ""
            if field_no == 1:
                out["symbol"] = val
            elif field_no == 2:
                out["trade_id"] = val
            elif field_no == 5:
                out["side"] = val
            elif field_no == 7:
                out["buyer"] = val
            elif field_no == 8:
                out["seller"] = val
        elif wt == 5:  # 32-bit (price)
            v, i = _read_f32_le(u8, i)
            if field_no == 3:
                out["price"] = v
        elif wt == 1:  # 64-bit skip
            i += 8
        else:
            break
    return out


# --- Health ---
@app.get("/healthz")
def healthz():
    return {"ok": True}


# --- Webapp page ---
@app.get("/webapp/depth", response_class=HTMLResponse)
def depth_webapp(request: Request, symbol: str):
    return templates.TemplateResponse(
        "depth.html",
        {
            "request": request,
            "symbol": symbol.upper(),
            "websocket_url": f"/ws/depth/{symbol.upper()}",
            # "market_url": f"/ws/market/{symbol}",
            # "trade_url": f"/ws/trade/{symbol}",
        },
    )


# --- DEPTH WS ---
@app.websocket("/ws/depth/{symbol}")
async def ws_depth(websocket: WebSocket, symbol: str):
    await websocket.accept()
    sym = (symbol or "").upper()
    cid = f"{sym}#{id(websocket) & 0xFFFFFF:x}"
    log.info("[%s]: client connected (DEPTH)", cid)

    depth_client = MatrixDepthClient(
        symbol=sym,
        connect_template_b64=settings.CONNECT_TEMPLATE_B64,
    )

    async def safe_send(obj) -> bool:
        if websocket.application_state != WebSocketState.CONNECTED:
            return False
        try:
            await websocket.send_json(obj)
            return True
        except WebSocketDisconnect:
            return False
        except Exception:
            log.exception("[%s]: send_json failed", cid)
            return False

    await safe_send({"status": "connected", "symbol": sym})

    backoff = 0.8
    try:
        while websocket.application_state == WebSocketState.CONNECTED:
            try:
                async for levels in depth_client.connect_and_stream():
                    # >>> HUBLARI BESLE <<<
                    try:
                        await depth_hub.set(sym, levels)
                    except Exception:
                        log.exception("[%s]: depth_hub.set failed", cid)

                    ok = await safe_send({"symbol": sym, "levels": levels})
                    if not ok:
                        return
                    backoff = 0.8
            except WebSocketDisconnect:
                return
            except Exception:
                log.error(
                    "[%s]: depth runner error; retrying shortly", cid, exc_info=True
                )
                await safe_send({"status": "reconnecting"})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.7, 10.0)
    finally:
        log.info("[%s]: client disconnected (DEPTH)", cid)


# --- TRADE WS (JSON standardize) ---
@app.websocket("/ws/trade/{symbol}")
async def ws_trade(ws: WebSocket, symbol: str):
    await ws.accept()
    sym = (symbol or "").upper()
    cid = f"TRADE#{sym}"
    log.info("[%s]: client connected", cid)

    # <-- BURADA: tuple/list gelirse düzelt
    raw_tmpl = (
        getattr(settings, "TRADE_CONNECT_TEMPLATE_B64", "")
        or settings.CONNECT_TEMPLATE_B64
    )
    if isinstance(raw_tmpl, (tuple, list)):
        raw_tmpl = raw_tmpl[0] if raw_tmpl else ""
    tmpl_b64 = (raw_tmpl or "").strip()

    client = MatrixTradeClient(
        symbol=sym,
        connect_template_b64=tmpl_b64,
    )

    # bytes gelirse son çare minidecoder; dict gelirse aynen kullanırız
    import struct

    def _read_varint(buf: bytes, i: int):
        x = 0
        s = 0
        while True:
            b = buf[i]
            i += 1
            x |= (b & 0x7F) << s
            if not (b & 0x80):
                break
            s += 7
        return x, i

    def _read_len(buf: bytes, i: int):
        ln, i = _read_varint(buf, i)
        j = i + ln
        return buf[i:j], j

    def _read_f32(buf: bytes, i: int):
        return float(struct.unpack_from("<f", buf, i)[0]), i + 4

    def _mini_decode(u8: bytes) -> dict:
        out = {}
        i = 0
        L = len(u8)
        while i < L:
            tag, i = _read_varint(u8, i)
            f, wt = tag >> 3, tag & 7
            if wt == 0:
                v, i = _read_varint(u8, i)
                if f == 4:
                    out["qty"] = v
                elif f == 6:
                    out["ts"] = v
            elif wt == 2:
                s, i = _read_len(u8, i)
                try:
                    s = s.decode("utf-8")
                except:
                    s = ""
                if f == 1:
                    out["symbol"] = s
                elif f == 2:
                    out["trade_id"] = s
                elif f == 5:
                    out["side"] = s
                elif f == 7:
                    out["buyer"] = s
                elif f == 8:
                    out["seller"] = s
            elif wt == 5:
                v, i = _read_f32(u8, i)
                if f == 3:
                    out["price"] = v
            elif wt == 1:
                i += 8
            else:
                break
        return out

    def _normalize(t: dict) -> dict:
        # sembol zorunlu değilse sabitle
        if not t.get("symbol"):
            t["symbol"] = sym
        # side tek harf (a/b) ve küçük
        if t.get("side"):
            t["side"] = str(t["side"]).lower()[:1]
        # ts mantıklı değilse şimdi
        try:
            ts = int(t.get("ts") or 0)
        except:
            ts = 0
        if ts < 1_500_000_000_000 or ts > 4_102_444_800_000:
            import time as _time

            t["ts"] = int(_time.time() * 1000)
        else:
            t["ts"] = ts
        # fallback anahtar isimleri (buyer/seller)
        t["buyer"] = (
            t.get("buyer")
            or t.get("buyer_code")
            or t.get("buyerTag")
            or t.get("b")
            or ""
        )
        t["seller"] = (
            t.get("seller")
            or t.get("seller_code")
            or t.get("sellerTag")
            or t.get("s")
            or ""
        )
        # sayı tipleri
        try:
            t["price"] = float(t.get("price") or 0.0)
        except:
            t["price"] = 0.0
        try:
            t["qty"] = int(t.get("qty") or 0)
        except:
            t["qty"] = 0
        return t

    backoff = 0.8
    try:
        while ws.application_state == WebSocketState.CONNECTED:
            try:
                async for item in client.connect_and_stream():
                    if isinstance(item, dict):
                        t = _normalize(item)
                        # >>> HUBLARI BESLE <<<
                        try:
                            await trade_hub.add(sym, t)
                        except Exception:
                            log.exception("[%s]: trade_hub.add failed", cid)
                        try:
                            await ws.send_json({"symbol": sym, "trade": t})
                        except WebSocketDisconnect:
                            return
                        except Exception:
                            log.exception("[%s]: send_json failed", cid)
                        continue

                    if isinstance(item, (bytes, bytearray)):
                        try:
                            t = _mini_decode(bytes(item))
                            if t:
                                t = _normalize(t)
                                try:
                                    await trade_hub.add(sym, t)
                                except Exception:
                                    log.exception(
                                        "[%s]: trade_hub.add failed (bytes)", cid
                                    )
                                await ws.send_json({"symbol": sym, "trade": t})
                                continue
                        except Exception:
                            pass
                        try:
                            import base64

                            b64 = base64.b64encode(bytes(item)).decode("ascii")
                            await ws.send_text(b64)
                        except WebSocketDisconnect:
                            return

            except WebSocketDisconnect:
                return
            except Exception:
                log.exception("[%s]: trade runner error; retry", cid)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.7, 10.0)
    finally:
        log.info("[%s]: client disconnected", cid)


def _vread(u8, i):
    x = 0
    s = 0
    while True:
        b = u8[i]
        i += 1
        x |= (b & 0x7F) << s
        if not (b & 0x80):
            break
        s += 7
    return x, i


def _f64(u8, i):
    v = struct.unpack_from("<d", u8, i)[0]
    return float(v), i + 8


def _decode_market_payload(raw: bytes) -> dict:
    """raw → {last, bid, ask, high, low, ceiling, floor, volume, prev_close, change_pct}"""
    u8 = raw
    i = 0
    L = len(u8)
    m = {}
    while i < L:
        tag, i = _vread(u8, i)
        f, wt = (tag >> 3), (tag & 7)
        if wt == 1:
            v, i = _f64(u8, i)
            m[f] = v
        elif wt == 0:
            v, i = _vread(u8, i)
            m[f] = float(v)
        elif wt == 2:
            ln, i = _vread(u8, i)
            i += ln
        elif wt == 5:
            i += 4
        else:
            break

    def first(*keys):
        for k in keys:
            v = m.get(k)
            if v is not None:
                return v
        return None

    last = first(5, 25)
    bid = first(10, 42)
    ask = first(6)
    high = first(8, 13, 54)
    low = first(12, 55)
    ceil = first(26, 21)
    floor = first(27, 22)
    vol = first(14, 48)
    prev = first(9, 62, 47)  # provider "prev_close" (ekranda alış olarak kullanıyorduk)
    # fark hesabında GERÇEK ÖNCEKİ = bid (bizim kural)
    change_pct = None
    if last is not None and bid not in (None, 0):
        change_pct = (last - bid) / bid * 100.0

    return {
        "last": last,
        "bid": bid,
        "ask": ask,
        "high": high,
        "low": low,
        "ceiling": ceil,
        "floor": floor,
        "volume": vol,
        "prev_close": bid,
        "change_pct": change_pct,
    }


async def _get_quote_once(symbol: str, timeout: float = 1.0) -> dict:
    """Market WS’den tek paket alır."""
    cli = MatrixMarketClient(
        symbol=symbol,
        connect_template_b64=getattr(settings, "MARKET_CONNECT_TEMPLATE_B64", "")
        or settings.CONNECT_TEMPLATE_B64,
    )
    try:

        async def _runner():
            async for payload in cli.connect_and_stream():
                return _decode_market_payload(payload)

        return await asyncio.wait_for(_runner(), timeout=timeout)
    except Exception:
        return {}


def _norm_trade(t: dict, sym: str) -> dict:
    if not t.get("symbol"):
        t["symbol"] = sym
    t["buyer"] = (
        t.get("buyer") or t.get("buyer_code") or t.get("buyerTag") or t.get("b") or ""
    )
    t["seller"] = (
        t.get("seller")
        or t.get("seller_code")
        or t.get("sellerTag")
        or t.get("s")
        or ""
    )
    try:
        t["price"] = float(t.get("price") or 0.0)
    except:
        t["price"] = 0.0
    try:
        t["qty"] = int(t.get("qty") or 0)
    except:
        t["qty"] = 0
    if t.get("side"):
        t["side"] = str(t["side"]).lower()[:1]
    try:
        ts = int(t.get("ts") or 0)
        if ts < 1_500_000_000_000 or ts > 4_102_444_800_000:
            import time as _time

            ts = int(_time.time() * 1000)
    except:
        import time as _time

        ts = int(_time.time() * 1000)
    t["ts"] = ts
    return t


async def _collect_last_trades(
    symbol: str, n: int = 5, timeout: float = 1.2
) -> list[dict]:
    """Kısa bir süre dinleyip ilk N işlemi alır."""
    client = MatrixTradeClient(
        symbol=symbol,
        connect_template_b64=(
            getattr(settings, "TRADE_CONNECT_TEMPLATE_B64", "")
            or settings.CONNECT_TEMPLATE_B64
        ),
    )
    out: list[dict] = []

    async def _runner():
        async for item in client.connect_and_stream():
            if isinstance(item, dict):
                out.append(_norm_trade(item, symbol))
            elif isinstance(item, (bytes, bytearray)):
                # minimal decoder (3=price f32, 4=qty varint, 6=ts varint, 5=side str, 7/8 buyer/seller str)
                buf = bytes(item)
                i = 0

                def v():
                    nonlocal i, buf
                    x = 0
                    s = 0
                    while True:
                        b = buf[i]
                        i += 1
                        x |= (b & 0x7F) << s
                        if not (b & 0x80):
                            break
                        s += 7
                    return x

                def s():
                    nonlocal i, buf
                    ln = v()
                    j = i + ln
                    b = buf[i:j]
                    i = j
                    try:
                        return b.decode("utf-8")
                    except:
                        return ""

                def f32():
                    nonlocal i, buf
                    val = struct.unpack_from("<f", buf, i)[0]
                    i += 4
                    return float(val)

                t = {}
                while i < len(buf):
                    tag = v()
                    f = tag >> 3
                    wt = tag & 7
                    if wt == 0:
                        val = v()
                        if f == 4:
                            t["qty"] = val
                        if f == 6:
                            t["ts"] = val
                    elif wt == 2:
                        val = s()
                        if f == 1:
                            t["symbol"] = val
                        elif f == 2:
                            t["trade_id"] = val
                        elif f == 5:
                            t["side"] = val
                        elif f == 7:
                            t["buyer"] = val
                        elif f == 8:
                            t["seller"] = val
                    elif wt == 5:
                        val = f32()
                        if f == 3:
                            t["price"] = val
                    elif wt == 1:
                        i += 8
                    else:
                        break
                if t:
                    out.append(_norm_trade(t, symbol))
            if len(out) >= n:
                break

    try:
        await asyncio.wait_for(_runner(), timeout=timeout)
    except Exception:
        pass
    return out


@app.get("/api/snapshot/depth.png")
async def snapshot_depth(
    symbol: str,
    size: str = Query("mobile", pattern="^(mobile|square|wide)$"),
    scale: int = Query(2, ge=1, le=3),
):
    sym = symbol.upper()

    levels = await depth_hub.get_last(sym, timeout=1.0) or []
    trades = await trade_hub.get_last(sym, limit=5) or []

    # Basit quote (eldeki verilerden)
    quote = {}
    try:
        last_price = (
            float(trades[0]["price"])
            if trades and trades[0].get("price") is not None
            else None
        )
    except Exception:
        last_price = None

    # Not: Eğer market snapshot akıyorsa oradan da besleyebilirsin.
    quote["last"] = last_price

    # Volümü yaklaşık hesap: son 5'in toplamı
    try:
        vol = sum(int(t.get("qty") or 0) for t in trades) or None
    except Exception:
        vol = None
    quote["volume"] = vol

    # Önceki kapanış (işlem yoksa boş kalsın)
    quote["prev_close"] = None

    png = render_depth_png(
        levels=levels, trades=trades, symbol=sym, quote=quote, size=size, scale=scale
    )
    return Response(content=png, media_type="image/png")


# --- Admin ---
def _assert_admin(x_api_key: str | None):
    if not x_api_key or x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/admin/jwt")
async def admin_set_jwt(body: dict, x_api_key: str = Header(None)):
    _assert_admin(x_api_key)
    jwt = body.get("jwt")
    if not jwt:
        raise HTTPException(status_code=400, detail="jwt required")
    token_manager.set(jwt)
    return {"ok": True}


@app.post("/admin/connect-template")
async def admin_set_template(body: dict, x_api_key: str = Header(None)):
    _assert_admin(x_api_key)
    b64 = body.get("b64")
    if not b64:
        raise HTTPException(status_code=400, detail="b64 required")
    settings.CONNECT_TEMPLATE_B64 = b64
    return {"ok": True}


@app.get("/diag")
def diag():
    def _exp(ts):
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(ts)))
        except Exception:
            return None

    tmpl_len = len(settings.CONNECT_TEMPLATE_B64 or "")
    jwt = settings.INITIAL_JWT or ""
    exp = None
    if jwt.count(".") == 2:
        try:
            payload = json.loads(base64.urlsafe_b64decode(jwt.split(".")[1] + "=="))
            exp = payload.get("exp")
        except Exception:
            pass
    return {
        "connect_template_len": tmpl_len,
        "jwt_present": bool(jwt),
        "jwt_exp_unix": exp,
        "jwt_exp_human": _exp(exp) if exp else None,
    }


def _auth_header_jwt() -> str:
    tok = (settings.INITIAL_JWT or "").strip()
    low = tok.lower()
    if low.startswith("bearer ") or low.startswith("jwt "):
        return tok
    return f"jwt {tok}"


@app.get("/api/news")
async def api_news(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    page_size: Optional[int] = Query(None),
    content: str = Query("ALL"),
    filters: Optional[str] = Query(None),
    mid: Optional[str] = Query(None),
    qid: Optional[str] = Query(None),
):
    page = max(1, page)
    if page_size is not None:
        try:
            size = int(page_size)
        except (TypeError, ValueError):
            pass
    size = max(1, min(size, 100))

    raw_filters: Dict[str, Any] = {}
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            raw_filters["raw"] = filters
        else:
            if isinstance(parsed_filters, dict):
                raw_filters.update(parsed_filters)
            else:
                raw_filters["raw"] = parsed_filters

    reserved_keys = {"page", "size", "page_size", "content", "mid", "qid", "filters"}
    for key, value in request.query_params.multi_items():
        if key in reserved_keys:
            continue
        _merge_filter_value(raw_filters, key, value)

    cleaned_filters = _cleanup_filters(raw_filters)
    filter_signature = cleaned_filters if cleaned_filters else {}

    def _pick_symbol(*candidates: Any) -> Optional[str]:
        for cand in candidates:
            if cand is None:
                continue
            if isinstance(cand, (list, tuple, set)):
                for item in cand:
                    picked = _pick_symbol(item)
                    if picked:
                        return picked
                continue
            try:
                text = str(cand)
            except Exception:
                continue
            text = text.strip()
            if not text:
                continue
            if "," in text:
                text = text.split(",", 1)[0].strip()
            if not text:
                continue
            return text.upper()
        return None

    symbol_value = _pick_symbol(
        filter_signature.get("symbol") if filter_signature else None,
        filter_signature.get("symbols") if filter_signature else None,
        filter_signature.get("code") if filter_signature else None,
        filter_signature.get("codes") if filter_signature else None,
        filter_signature.get("ticker") if filter_signature else None,
        raw_filters.get("symbol"),
        raw_filters.get("symbols"),
        raw_filters.get("code"),
        raw_filters.get("codes"),
        raw_filters.get("ticker"),
        request.query_params.get("symbol"),
    )

    if not symbol_value:
        log.error("news: symbol missing in request")
        return JSONResponse({"error": "symbol_required"}, status_code=400)
    content_value = (content or "ALL").strip() or "ALL"

    cache_key = _news_cache_key(content_value, filter_signature)
    now = time.time()
    qid_value = qid.strip() if isinstance(qid, str) and qid.strip() else None
    cache_hit = False
    if not qid_value:
        cached = _NEWS_QID_CACHE.get(cache_key)
        if cached:
            cached_ts = cached.get("ts", 0.0)
            if now - cached_ts < _NEWS_QID_TTL:
                candidate = cached.get("qid")
                if isinstance(candidate, str) and candidate:
                    qid_value = candidate
                    cache_hit = True

    jwt_raw = None
    try:
        jwt_raw = token_manager.get()
    except Exception:
        log.exception("news: token_manager.get() failed")

    auth_header = _normalize_jwt_header(jwt_raw) or _auth_header_jwt()
    if not auth_header or auth_header.strip().lower() in {"jwt", "bearer"}:
        log.error("news: jwt unavailable")
        return JSONResponse({"error": "jwt_unavailable"}, status_code=502)

    headers = _news_headers(auth_header)
    mid_value = mid or str(int(time.time() * 1000))
    base_params = {"mid": mid_value, "ngsw-bypass": "true"}

    upstream_filters: Optional[Dict[str, Any]] = None
    page_payload: Optional[Dict[str, Any]] = None

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as cli:
            if not qid_value:
                search_params: Dict[str, Any] = dict(base_params)
                search_params.update(
                    {
                        "language": "tr",
                        "withComment": "true",
                        "count": str(size),
                        "query": f"symbol:{symbol_value}",
                    }
                )
                try:
                    resp_search = await cli.post(
                        "https://api.matriksdata.com/dumrul/v2/news/search",
                        headers=headers,
                        params=search_params,
                    )
                except httpx.TimeoutException:
                    return JSONResponse(
                        {"error": "timeout", "stage": "search"}, status_code=504
                    )
                except Exception:
                    log.exception("news search upstream error")
                    return JSONResponse(
                        {"error": "proxy_failed", "stage": "search"}, status_code=502
                    )

                if resp_search.status_code != 200:
                    log.warning(
                        "news search upstream %s: %s",
                        resp_search.status_code,
                        resp_search.text[:200],
                    )
                    return JSONResponse(
                        {
                            "error": "upstream",
                            "stage": "search",
                            "status": resp_search.status_code,
                        },
                        status_code=502,
                    )

                try:
                    search_data = _parse_upstream_json(resp_search)
                except Exception:
                    log.exception("news search payload decode failed")
                    return JSONResponse(
                        {"error": "bad_payload", "stage": "search"}, status_code=502
                    )

                qid_value = _extract_qid(search_data)
                if not qid_value:
                    log.error("news search missing qid: %s", str(search_data)[:200])
                    return JSONResponse({"error": "qid_missing"}, status_code=502)

                upstream_filters = _extract_filters(search_data)
                ts_now = time.time()
                _NEWS_QID_CACHE[cache_key] = {"qid": qid_value, "ts": ts_now}
                if len(_NEWS_QID_CACHE) > 64:
                    for ck, entry in list(_NEWS_QID_CACHE.items()):
                        if ts_now - entry.get("ts", 0.0) > (_NEWS_QID_TTL * 4):
                            _NEWS_QID_CACHE.pop(ck, None)

            page_params = dict(base_params)
            page_params.update(
                {
                    "qid": qid_value,
                    "page": page,
                    "size": size,
                    "content": content_value,
                    "filter": json.dumps(filter_signature or {}, ensure_ascii=False),
                }
            )

            try:
                resp_page = await cli.get(
                    "https://api.matriksdata.com/dumrul/v2/news/search/page.gz",
                    headers=headers,
                    params=page_params,
                )
            except httpx.TimeoutException:
                return JSONResponse(
                    {"error": "timeout", "stage": "page"}, status_code=504
                )
            except Exception:
                log.exception("news page upstream error")
                return JSONResponse(
                    {"error": "proxy_failed", "stage": "page"}, status_code=502
                )

            if resp_page.status_code != 200:
                log.warning(
                    "news page upstream %s: %s",
                    resp_page.status_code,
                    resp_page.text[:200],
                )
                return JSONResponse(
                    {
                        "error": "upstream",
                        "stage": "page",
                        "status": resp_page.status_code,
                    },
                    status_code=502,
                )

            try:
                parsed_page = _parse_upstream_json(resp_page)
            except Exception:
                log.exception("news page payload decode failed")
                return JSONResponse(
                    {"error": "bad_payload", "stage": "page"}, status_code=502
                )

            page_payload = parsed_page if isinstance(parsed_page, dict) else {}
            upstream_filters = _extract_filters(page_payload) or upstream_filters

    except Exception:
        log.exception("news proxy unexpected error")
        return JSONResponse({"error": "proxy_failed"}, status_code=502)

    if page_payload is None:
        return JSONResponse({"error": "empty_payload"}, status_code=502)

    items = _extract_items(page_payload)
    if not isinstance(items, list):
        items = []

    meta_section = _extract_pagination_meta(page_payload)
    page_index = _first_numeric(
        [
            "page",
            "pageIndex",
            "page_number",
            "number",
            "index",
        ],
        meta_section,
        page_payload,
    )
    size_value = _first_numeric(
        [
            "size",
            "pageSize",
            "perPage",
            "limit",
        ],
        meta_section,
        page_payload,
    )
    total_items = _first_numeric(
        [
            "total",
            "totalItems",
            "totalElements",
            "total_records",
        ],
        meta_section,
        page_payload,
    )
    total_pages = _first_numeric(
        [
            "totalPages",
            "pageCount",
            "pages",
        ],
        meta_section,
        page_payload,
    )

    if page_index is None:
        page_index = page
    if size_value is None:
        size_value = size

    page_index_for_calc = max(page_index or 1, 1)
    size_for_calc = max(size_value or size, 1)

    has_more = False
    if total_items is not None and total_items >= 0:
        consumed = (page_index_for_calc - 1) * size_for_calc + len(items)
        has_more = consumed < total_items
    elif total_pages is not None and total_pages >= 0:
        has_more = page_index_for_calc < max(total_pages, 0)
    else:
        has_more = len(items) >= size_for_calc

    pagination = {
        "page": page_index,
        "page_size": size_value,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_more": has_more,
        "cache_hit": cache_hit,
    }

    filters_out: Dict[str, Any] = {
        "content": content_value,
        "applied": filter_signature,
    }
    if upstream_filters:
        filters_out["upstream"] = upstream_filters

    meta_extra = {
        "mid": mid_value,
        "received_at": int(time.time() * 1000),
    }

    return {
        "qid": qid_value,
        "items": items,
        "pagination": pagination,
        "filters": filters_out,
        "meta": meta_extra,
    }


@app.get("/webapp/akd", response_class=HTMLResponse)
def akd_webapp(request: Request, symbol: str = "ASELS"):
    return templates.TemplateResponse(
        "akd.html",
        {
            "request": request,
            "symbol": (symbol or "ASELS").upper(),
            "api_base": settings.API_BASE.rstrip("/"),
            "webapp_base": settings.WEBAPP_BASE.rstrip("/"),
        },
    )


@app.get("/api/akd")
async def api_akd(
    symbol: str,
    top: int = 5,
    startseconds: Optional[int] = None,
    endseconds: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    if not symbol:
        return JSONResponse({"error": "symbol required"}, status_code=400)

    params = {"symbol": symbol.upper(), "top": str(max(1, min(top, 100)))}
    if startseconds and endseconds:
        params["startseconds"] = str(startseconds)
        params["endseconds"] = str(endseconds)
    if start and end:
        params["start"] = start
        params["end"] = end
    params["mid"] = str(int(time.time() * 1000))
    params["ngsw-bypass"] = "true"

    headers = {
        "Authorization": _auth_header_jwt(),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.matrikswebtrader.com",
        "Referer": "https://app.matrikswebtrader.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as cli:
            r = await cli.get(
                "https://api.matriksdata.com/dumrul/v2/akd.gz",
                params=params,
                headers=headers,
            )
        if r.status_code != 200:
            log.warning("AKD upstream %s: %s", r.status_code, r.text[:200])
            return JSONResponse({"error": "upstream"}, status_code=r.status_code)
        return Response(content=r.content, media_type="application/json")
    except Exception:
        log.exception("AKD upstream network error for %s", symbol)
        return JSONResponse({"error": "network"}, status_code=502)


def _auth_header() -> str:
    tok = (settings.INITIAL_JWT or "").strip()
    return tok if tok.lower().startswith("bearer ") else f"Bearer {tok}"


@app.get("/logo/{symbol}")
async def logo(symbol: str):
    sym = (symbol or "").upper().strip()
    if not sym:
        return Response("symbol required", status_code=400)

    headers = {
        "Authorization": _auth_header(),
        "Accept": "image/*,image/svg+xml,*/*;q=0.8",
        "Origin": "https://app.matrikswebtrader.com",
        "Referer": "https://app.matrikswebtrader.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as cli:
            r = await cli.get(MATRIX_LOGO_URL, params={"symbol": sym}, headers=headers)
    except Exception:
        log.exception("logo upstream network error for %s", sym)
        return Response(status_code=HTTP_204_NO_CONTENT)

    if r.status_code == 200 and r.content:
        ctype = (r.headers.get("content-type") or "").lower()
        if "svg" in ctype:
            mt = "image/svg+xml"
        elif "png" in ctype:
            mt = "image/png"
        elif "jpeg" in ctype or "jpg" in ctype:
            mt = "image/jpeg"
        elif "gif" in ctype:
            mt = "image/gif"
        else:
            mt = "application/octet-stream"
        return Response(
            content=r.content,
            media_type=mt,
            headers={"Cache-Control": "public, max-age=300"},
        )

    log.warning("logo upstream %s for %s; body=%r", r.status_code, sym, r.text[:200])
    return Response(status_code=HTTP_204_NO_CONTENT)


@app.websocket("/ws/heatmap")
async def ws_heatmap(ws: WebSocket):
    await ws.accept()
    cid = f"HEATMAP#{id(ws) & 0xFFFFFF:x}"
    log.info("[%s]: client connected (HEATMAP)", cid)

    async with _heatmap_clients_lock:
        _heatmap_clients.add(ws)

    try:
        await _ensure_heatmap_tasks()
        try:
            await ws.send_json({"type": "meta", "symbols": list(HEATMAP_SYMBOLS)})
        except WebSocketDisconnect:
            return
        except Exception:
            log.exception("[%s]: failed to send heatmap meta", cid)
        else:
            try:
                await _heatmap_send_snapshot(ws)
            except WebSocketDisconnect:
                return
            except Exception:
                log.exception("[%s]: failed to send initial heatmap snapshot", cid)

        while True:
            try:
                msg = await ws.receive()
            except WebSocketDisconnect:
                break
            except Exception:
                log.exception("[%s]: heatmap receive error", cid)
                break
            if not msg:
                continue
            if msg.get("type") == "websocket.disconnect":
                break
    finally:
        async with _heatmap_clients_lock:
            _heatmap_clients.discard(ws)
        log.info("[%s]: client disconnected (HEATMAP)", cid)


@app.websocket("/ws/market/{symbol}")
async def ws_market(ws: WebSocket, symbol: str):
    await ws.accept()
    sym = (symbol or "").upper().strip()
    log.info("[MARKET#%s]: client connected", sym)

    client = MatrixMarketClient(
        symbol=sym,
        connect_template_b64=getattr(settings, "MARKET_CONNECT_TEMPLATE_B64", "")
        or settings.CONNECT_TEMPLATE_B64,
    )
    try:
        async for payload in client.connect_and_stream():
            try:
                b64 = base64.b64encode(payload).decode("ascii")
                await ws.send_text(b64)
            except (
                WebSocketDisconnect,
                RuntimeError,
            ):  # RuntimeError: close after close
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("[MARKET#%s]: market stream error", sym)
    finally:
        log.info("[MARKET#%s]: client disconnected", sym)


# --- Webapp page: TAKAS ---
@app.get("/webapp/takas", response_class=HTMLResponse)
def takas_webapp(request: Request, symbol: str = "ASELS"):
    # tek bir HTML dosyası döndürmeyeceğiz; bunu templates tarafında "takas.html" olarak servis edeceksen
    # TemplateResponse kullan. Eğer tek-dosya HTML’i doğrudan döndüreceksen burada string döndür.
    # Ben aşağıda tam HTML’i verdim; pratikte templates/takas.html koyup TemplateResponse ile döndürmeni öneririm.
    return templates.TemplateResponse(
        "takas.html",
        {
            "request": request,
            "symbol": (symbol or "ASELS").upper(),
            "api_base": settings.API_BASE.rstrip("/"),
            "webapp_base": settings.WEBAPP_BASE.rstrip("/"),
        },
    )


def _auth_header_jwt_takas() -> str:
    tok = (settings.INITIAL_JWT or "").strip()
    low = tok.lower()
    if low.startswith("bearer ") or low.startswith("jwt "):
        return tok
    return f"jwt {tok}"


# --- TAKAS Proxy ---
@app.get("/api/takas")
async def api_takas(
    symbol: str,
    start: str,  # YYYY-MM-DD
    end: str,  # YYYY-MM-DD
    mid: Optional[str] = None,
):
    """
    Matriks 'dumrul/v1/agent-assets.gz' uçlarına proxy.
    Zorunlu parametreler: symbol, start, end
    """
    if not symbol or not start or not end:
        return JSONResponse({"error": "params"}, status_code=400)

    params = {
        "symbol": symbol.upper(),
        "date": f"{start},{end}",
        "mid": mid or str(int(time.time() * 1000)),
        "ngsw-bypass": "true",
    }

    url = "https://api.matriksdata.com/dumrul/v1/agent-assets.gz"
    headers = {
        "Authorization": _auth_header_jwt_takas(),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Origin": "https://app.matrikswebtrader.com",
        "Referer": "https://app.matrikswebtrader.com/",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as cli:
            r = await cli.get(url, params=params, headers=headers)
        if r.status_code != 200:
            log.warning("TAKAS upstream %s: %s", r.status_code, r.text[:240])
            return JSONResponse({"error": "upstream"}, status_code=r.status_code)
        return Response(content=r.content, media_type="application/json")
    except httpx.TimeoutException:
        log.exception("TAKAS timeout")
        return JSONResponse({"error": "timeout"}, status_code=504)
    except Exception:
        log.exception("TAKAS network error for %s", symbol)
        return JSONResponse({"error": "network"}, status_code=502)


# --- Webapp page: PGC ---
@app.get("/webapp/pgc", response_class=HTMLResponse)
def pgc_webapp(request: Request):
    return templates.TemplateResponse(
        "pgc.html",
        {
            "request": request,
            "api_base": settings.API_BASE.rstrip("/"),
            "webapp_base": settings.WEBAPP_BASE.rstrip("/"),
        },
    )


# --- PGC Proxy (trade-distribution/equities) ---
@app.get("/api/pgc")
async def api_pgc(
    symbolType: str = Query("T,S,V,M,R"),
    top: int = Query(5, ge=1, le=100),
    start: Optional[str] = None,  # YYYY-MM-DD (range modu)
    end: Optional[str] = None,
    startSeconds: Optional[int] = None,  # periyot (son X dk)
    endSeconds: Optional[int] = None,
):
    """
    Para Giriş-Çıkış (equities) proxy.
    - Tarih aralığı için start/end,
    - 'Son N Dakika' için startSeconds/endSeconds gönder.
    """
    params = {
        "symbolType": symbolType,
        "top": str(top),
        "mid": str(int(time.time() * 1000)),
        "ngsw-bypass": "true",
    }
    if start and end:
        params["start"] = start
        params["end"] = end
    if startSeconds and endSeconds:
        params["startSeconds"] = str(startSeconds)
        params["endSeconds"] = str(endSeconds)

    url = "https://api.matriksdata.com/dumrul/v1/trade-distribution/equities"
    headers = {
        "Authorization": _auth_header_jwt(),
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://app.matrikswebtrader.com",
        "Referer": "https://app.matrikswebtrader.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as cli:
            r = await cli.get(url, params=params, headers=headers)
        if r.status_code != 200:
            log.warning("PGC upstream %s: %s", r.status_code, r.text[:200])
            return JSONResponse({"error": "upstream"}, status_code=r.status_code)
        return Response(content=r.content, media_type="application/json")
    except Exception:
        log.exception("PGC upstream network error")
        return JSONResponse({"error": "network"}, status_code=502)
