# run.py
import uvicorn
from app.web import app as fastapi_app
from app.bot import setup_webhook_app, on_startup, on_shutdown
# run.py
from app.logging_setup import *  # <-- ekle
from app.web import app as fastapi_app

setup_webhook_app(fastapi_app)

@fastapi_app.on_event("startup")
async def _startup():
    await on_startup()

@fastapi_app.on_event("shutdown")
async def _shutdown():
    await on_shutdown()

if __name__ == "__main__":
    uvicorn.run("run:fastapi_app", host="0.0.0.0", port=8000, reload=False)
