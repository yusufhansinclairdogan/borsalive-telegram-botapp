from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import asyncio, logging
from fastapi import Header, HTTPException
import base64
from .config import settings
from .depth_proxy import token_manager  # aynı instance
import base64, json, time
from fastapi import APIRouter
from .config import settings
from .depth_proxy import MatrixDepthClient
from .snapshot import render_depth_png

log = logging.getLogger("app.web")
app = FastAPI(title="borsalive-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.WEBAPP_BASE, "https://web.telegram.org", "https://web.telegram.org.a", "https://web.telegram.org/k/"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
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
    log.info("WS client connected for %s", sym)

    client = MatrixDepthClient(
        symbol=sym,
        connect_template_b64=settings.CONNECT_TEMPLATE_B64,
    )

    backoff = 1.0
    try:
        while True:
            try:
                async for levels in client.connect_and_stream():
                    await websocket.send_json({"symbol": sym, "levels": levels})
                    backoff = 1.0
            except Exception:
                log.exception("ws_depth error for %s", sym)  # <-- TÜM stacktrace
                try:
                    await websocket.send_json({"status": "reconnecting"})
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)
    except WebSocketDisconnect:
        log.info("WS disconnected for %s", sym)
        return

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
    settings.CONNECT_TEMPLATE_B64 = b64  # runtime set
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