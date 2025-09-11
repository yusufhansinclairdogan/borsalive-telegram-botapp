# app/matriks_autoauth.py
from __future__ import annotations
import asyncio, logging, re, contextlib
from typing import Optional
from playwright.async_api import async_playwright
from .config import settings

log = logging.getLogger("autoauth")

_JWT_RE = re.compile(
    r"\b(jwt|bearer)\s+([A-Za-z0-9_\-\.]+)\.([A-Za-z0-9_\-\.]+)\.([A-Za-z0-9_\-\.]+)\b",
    re.I,
)


async def fetch_jwt_via_browser(timeout_sec: int = 40) -> Optional[str]:
    """
    Headless Chromium ile app.matrikswebtrader.com’a login olur,
    api.matriksdata.com isteklerindeki Authorization header’dan JWT yakalar.
    """
    user = settings.MATRIX_LOGIN_USER
    pwd = settings.MATRIX_LOGIN_PASS
    if not user or not pwd:
        log.warning("MATRIX_LOGIN_USER/PASS tanımlı değil.")
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        caught_jwt: Optional[str] = None

        def _scrape_auth_header(request):
            nonlocal caught_jwt
            try:
                url = request.url
                if "api.matriksdata.com" in url:
                    ah = request.headers.get("authorization") or ""
                    m = _JWT_RE.search(ah)
                    if m:
                        # m.group(2)+'.'+group(3)+'.'+group(4) -> saf token
                        token = ".".join(m.groups()[1:4])
                        caught_jwt = token
            except Exception:
                pass

        page.on("request", _scrape_auth_header)

        try:
            # Giriş sayfası
            await page.goto(
                "https://app.matrikswebtrader.com/", timeout=timeout_sec * 1000
            )

            # Bazı sürümlerde login modal/iframe vs olabilir; yaygın input isimlerine göre brute-find:
            # Kullanıcı adı
            user_sel_candidates = [
                "input[name='username']",
                "input[type='text']",
                "input[placeholder*='Kullanıcı']",
                "input[placeholder*='User']",
            ]
            pass_sel_candidates = [
                "input[name='password']",
                "input[type='password']",
                "input[placeholder*='Şifre']",
                "input[placeholder*='Pass']",
            ]
            login_btn_candidates = [
                "button[type='submit']",
                "button:has-text('Giriş')",
                "button:has-text('Login')",
            ]

            async def _first_visible(cands):
                for s in cands:
                    with contextlib.suppress(Exception):
                        el = await page.wait_for_selector(
                            s, state="visible", timeout=3000
                        )
                        if el:
                            return el
                return None

            uel = await _first_visible(user_sel_candidates)
            pel = await _first_visible(pass_sel_candidates)

            if not uel or not pel:
                # Bazı durumlarda app service worker ile kendiliğinden istek atıyor; JWT’yi yine yakalayabiliriz.
                await page.wait_for_timeout(5000)

            if uel and pel:
                await uel.fill(user)
                await pel.fill(pwd)
                btn = await _first_visible(login_btn_candidates)
                if btn:
                    await btn.click()
                else:
                    # enter
                    await pel.press("Enter")

            # JWT yakalanana kadar bekle
            for _ in range(int(timeout_sec * 2)):  # ~40s
                if caught_jwt:
                    break
                await page.wait_for_timeout(500)

            if not caught_jwt:
                log.warning("JWT yakalanamadı (timeout).")
                return None
            return caught_jwt
        finally:
            await ctx.close()
            await browser.close()
