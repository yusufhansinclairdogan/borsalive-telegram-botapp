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
from typing import Optional, Dict, Any, List
import asyncio
import base64
import struct
import time
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
