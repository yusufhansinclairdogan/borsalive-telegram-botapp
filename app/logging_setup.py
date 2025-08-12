# app/logging_setup.py
import logging, os, sys, json
from logging.handlers import RotatingFileHandler

# ---------- Ayarlar ----------
LVL = os.getenv("LOG_LEVEL", "DEBUG").upper()
LOG_JSON = os.getenv("LOG_JSON", "0") in ("1", "true", "True")
LOG_FILE = os.getenv("LOG_FILE", "")  # ör: /var/log/borsalive/app.log
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10MB
LOG_BACKUPS = int(os.getenv("LOG_BACKUPS", "5"))

# ---------- Formatlayıcılar ----------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "lvl": record.levelname,
            "log": record.name,
            "msg": record.getMessage(),
        }
        # bağlam (LoggerAdapter -> extra)
        for k in ("conn", "symbol"):
            v = getattr(record, k, None)
            if v is not None:
                data[k] = v
        return json.dumps(data, ensure_ascii=False)

class ConsoleFormatter(logging.Formatter):
    # ör: 2025-08-11 13:44:00 INFO app.web[ASTOR#7f3a1a] mesaj
    def format(self, record: logging.LogRecord) -> str:
        tag = []
        sym = getattr(record, "symbol", None)
        cid = getattr(record, "conn", None)
        if sym: tag.append(sym)
        if cid: tag.append(cid)
        ctx = f"[{'#'.join(tag)}]" if tag else ""
        base = f"%(asctime)s %(levelname)s %(name)s{ctx}: %(message)s"
        formatter = logging.Formatter(base)
        return formatter.format(record)

fmt = JsonFormatter() if LOG_JSON else ConsoleFormatter()

# ---------- Root ----------
root = logging.getLogger()
root.setLevel(getattr(logging, LVL, logging.DEBUG))

# Console
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(fmt)
root.addHandler(sh)

# File (opsiyonel)
if LOG_FILE:
    fh = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS)
    fh.setFormatter(fmt)
    root.addHandler(fh)

# Gürültüyü kıs
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("websockets").setLevel(logging.INFO)

# Bizim ana loggers
logging.getLogger("depth_proxy").setLevel(getattr(logging, LVL, logging.DEBUG))
logging.getLogger("app.web").setLevel(getattr(logging, LVL, logging.DEBUG))

# Bağlamlı logger helper (isteğe bağlı)
def with_ctx(logger: logging.Logger, **ctx) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, ctx)
