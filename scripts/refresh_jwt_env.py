#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import re
import sys
import time
import json
import tempfile
import shutil
from pathlib import Path

import requests
from playwright.async_api import async_playwright

# ----------------- AYARLAR -----------------
ENV_PATH         = Path(os.getenv("ENV_PATH", "/borsalive/.env"))
API_BASE         = os.getenv("API_BASE", "https://borsalive.app")
ADMIN_API_KEY    = os.getenv("ADMIN_API_KEY", "")  # .env'deki ile aynı olmalı
MATRIKS_URL      = os.getenv("MATRIKS_URL", "https://app.matrikswebtrader.com/tr/login")
MATRIKS_USER     = os.getenv("MATRIKS_USER", "355289")
MATRIKS_PASS     = os.getenv("MATRIKS_PASS", "wt1vU62Y")
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "1") != "0"

REQUEST_TIMEOUT  = 30

# Bazı sistemlerde sandbox kütüphaneleri yok, güvenli default:
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-setuid-sandbox",
]

def log(msg: str):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)

# ----------------- YARDIMCI -----------------

def _atomic_write_text(path: Path, content: str, backup: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
        shutil.copy2(path, backup_path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass

def _env_replace_initial_jwt(env_text: str, new_jwt: str) -> str:
    line = f"INITIAL_JWT={new_jwt}"
    if re.search(r"^INITIAL_JWT=.*$", env_text, flags=re.M):
        return re.sub(r"^INITIAL_JWT=.*$", line, env_text, flags=re.M)
    # Yoksa en alta ekle
    sep = "" if env_text.endswith("\n") else "\n"
    return env_text + sep + line + "\n"

def _hot_reload_jwt(jwt: str):
    if not ADMIN_API_KEY:
        log("UYARI: ADMIN_API_KEY boş; hot-reload atlanıyor.")
        return
    url = f"{API_BASE}/admin/jwt"
    try:
        r = requests.post(
            url,
            headers={"x-api-key": ADMIN_API_KEY, "content-type": "application/json"},
            data=json.dumps({"jwt": jwt}),
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            log("Hot-reload OK (/admin/jwt).")
        else:
            log(f"Hot-reload HATA: {r.status_code} {r.text[:200]}")
    except Exception as e:
        log(f"Hot-reload istisna: {e}")

# ----------------- JWT GETİR (Playwright) -----------------

async def fetch_jwt_via_playwright() -> str:
    token_box = {"jwt": None}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            args=CHROMIUM_ARGS
        )
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        def sniff_request(request):
            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            if auth and auth.lower().startswith("jwt "):
                token_box["jwt"] = auth.split(" ", 1)[1].strip()

        page.on("request", sniff_request)

        log(f"Gidiliyor: {MATRIKS_URL}")
        await page.goto(MATRIKS_URL, wait_until="domcontentloaded", timeout=60000)

        # Username & password alanlarını doldur
        await page.wait_for_selector("#mxcustom1", timeout=10000)
        await page.fill("#mxcustom1", MATRIKS_USER)
        await page.fill("#mxcustom2", MATRIKS_PASS)

        # Giriş butonuna tıkla
        await page.click(".primary-button.mobile-button-fix")

        # JWT yakalayana kadar bekle
        for _ in range(200):  # ~20 saniye bekleme
            if token_box["jwt"]:
                break
            await asyncio.sleep(0.1)

        await context.close()
        await browser.close()

    if not token_box["jwt"]:
        raise RuntimeError("JWT yakalanamadı (Authorization header görülmedi).")

    return token_box["jwt"]

# ----------------- ANA AKIŞ -----------------

async def main():
    log("Otomatik JWT yenileme başlıyor…")

    try:
        jwt = await fetch_jwt_via_playwright()
        log(f"Yeni JWT alındı; uzunluk={len(jwt)}")

        # ENV güncelle
        env_text = ""
        if ENV_PATH.exists():
            env_text = ENV_PATH.read_text(encoding="utf-8")
        new_text = _env_replace_initial_jwt(env_text, jwt)
        _atomic_write_text(ENV_PATH, new_text, backup=True)
        log(f".env güncellendi: {ENV_PATH}")

        # Çalışan uygulamaya da anında uygula
        _hot_reload_jwt(jwt)

        log("Tamamlandı ✅")
    except Exception as e:
        log(f"HATA: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
