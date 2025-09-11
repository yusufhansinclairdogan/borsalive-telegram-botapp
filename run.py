# run.py
import uvicorn
from app.web import app as fastapi_app
from app.bot import setup_webhook_app, on_startup, on_shutdown
from app.logging_setup import *  # noqa
from app.depth_proxy import token_manager
from app.auto_jwt_refresher import AutoJWTRefresher

# YENİ: sembol doğrulama router'ı
from app.routers import symbols as symbols_router

setup_webhook_app(fastapi_app)

# YENİ: router'ı app'e bağla
fastapi_app.include_router(symbols_router.router)

_refresher = AutoJWTRefresher(token_manager)

@fastapi_app.on_event("startup")
async def _startup():
    _refresher.start()
    await on_startup()

@fastapi_app.on_event("shutdown")
async def _shutdown():
    await _refresher.stop()
    await on_shutdown()

if __name__ == "__main__":
    uvicorn.run("run:fastapi_app", host="0.0.0.0", port=8000, reload=False)
