# app/web.py
from __future__ import annotations
import asyncio, logging, random, time, base64, json
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Header, HTTPException, APIRouter
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from .config import settings
from .depth_proxy import MatrixDepthClient, token_manager
from .snapshot import render_depth_png
from .logging_setup import with_ctx

router = APIRouter()
log = logging.getLogger("app.web")
app = FastAPI(title="borsalive-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.WEBAPP_BASE, "https://web.telegram.org", "https://web.telegram.org.a", "https://web.telegram.org/k/"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# klasörler (senin yerleşimine göre)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.get("/webapp/depth", response_class=HTMLResponse)
def depth_webapp(request: Request, symbol: str):
    return templates.TemplateResponse("depth.html", {
        "request": request,
        "symbol": symbol.upper(),
        "websocket_url": f"/ws/depth/{symbol.upper()}",
    })

@app.websocket("/ws/depth/{symbol}")
async def ws_depth(websocket: WebSocket, symbol: str):
    await websocket.accept()
    sym = symbol.upper()
    # bağlantı kimliği: kısa heks
    conn = hex(random.getrandbits(24))[2:]
    L = with_ctx(log, symbol=sym, conn=conn)

    L.info("WS client connected")
    client = MatrixDepthClient(symbol=sym, connect_template_b64=settings.CONNECT_TEMPLATE_B64)

    async def safe_send(obj) -> bool:
        if websocket.application_state != WebSocketState.CONNECTED:
            return False
        try:
            await websocket.send_json(obj)
            return True
        except WebSocketDisconnect:
            return False
        except RuntimeError as e:
            L.warning('Client closed while sending: %s', e)
            return False
        except Exception:
            L.exception("send_json failed")
            return False

    backoff = 1.0
    try:
        # UI rozeti için
        await safe_send({"status": "connected", "symbol": sym})

        while websocket.application_state == WebSocketState.CONNECTED:
            try:
                async for levels in client.connect_and_stream():
                    if not await safe_send({"symbol": sym, "levels": levels}):
                        return
                    backoff = 1.0
            except WebSocketDisconnect:
                L.info("WS disconnected by client")
                return
            except Exception:
                L.exception("ws_depth error")
                await safe_send({"status": "reconnecting"})
                await asyncio.sleep(backoff + random.uniform(0, 0.5))
                backoff = min(backoff * 1.7, 10.0)
    finally:
        L.info("WS disconnected")

@app.get("/api/snapshot/depth.png")
def snapshot_depth(symbol: str):
    png = render_depth_png([], symbol.upper())
    return Response(content=png, media_type="image/png")

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
        h,p,s = jwt.split(".")
        pad = lambda s: s + "="*((4 - len(s)%4)%4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(pad(p)))
            exp = payload.get("exp")
        except Exception:
            pass
    return {
        "connect_template_len": tmpl_len,
        "jwt_present": bool(jwt),
        "jwt_exp_unix": exp,
        "jwt_exp_human": _exp(exp) if exp else None,
    } 
