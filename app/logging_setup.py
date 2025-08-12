# app/logging_setup.py
import logging, os

LVL = os.getenv("LOG_LEVEL", "DEBUG").upper()
FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logging.basicConfig(level=getattr(logging, LVL, logging.DEBUG), format=FMT)

# Kendi loggerlarımız
logging.getLogger("depth_proxy").setLevel(logging.DEBUG)
logging.getLogger("app.web").setLevel(logging.DEBUG)

# Uvicorn / websockets
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("websockets.client").setLevel(logging.INFO)
