# app/routers/symbols.py
from fastapi import APIRouter, Response, Query
import httpx, json, time, logging
from typing import Optional
from app.config import settings
from app.depth_proxy import token_manager  # TokenManager (get() mevcut)

router = APIRouter()

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
    ngsw_bypass: Optional[bool] = Query(True, alias="ngsw-bypass")
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
                content=json.dumps({"error": "upstream_non_200", "status": r.status_code}),
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
