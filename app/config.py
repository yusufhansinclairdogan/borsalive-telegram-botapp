# app/config.py
import os, json

class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    WEBAPP_BASE = os.getenv("WEBAPP_BASE", "https://borsalive.app")
    API_BASE = os.getenv("API_BASE", "https://borsalive.app")
    WEBHOOK_RELATIVE_PATH = os.getenv("WEBHOOK_RELATIVE_PATH", "/bot/webhook")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")

    # MATRİKS
    MATRIX_DEPTH_URL = os.getenv("MATRIX_DEPTH_URL", "wss://rtstream.radix.matriksdata.com/depth")
    MATRIX_ORIGIN = os.getenv("MATRIX_ORIGIN", "https://app.matrikswebtrader.com")
    MATRIX_SUBPROTOCOL = os.getenv("MATRIX_SUBPROTOCOL", "mqttv3.1")

    # Admin/JWT
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
    CONNECT_TEMPLATE_B64 = os.getenv("CONNECT_TEMPLATE_B64", "")
    INITIAL_JWT = os.getenv("INITIAL_JWT", "")

    # Fallback frames (JSON string -> list)
    try:
        DEPTH_SUB_FRAMES_ASTOR = json.loads(os.getenv("DEPTH_SUB_FRAMES_ASTOR", "[]"))
    except Exception:
        DEPTH_SUB_FRAMES_ASTOR = []

settings = Settings()
