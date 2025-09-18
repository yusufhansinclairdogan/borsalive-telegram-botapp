# app/bot.py
import logging
import httpx
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    Update,
)
from fastapi import FastAPI, Request
from starlette.responses import Response

from .config import settings
from .snapshot import render_depth_png
from .depth_hub import hub as depth_hub
from .trade_hub import trade_hub  # mevcutsa sorun olmaz

# ----------------------------------------------------

log = logging.getLogger("bot")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
router = Router()

# -------------------- Keyboards -------------------- #


def depth_keyboard(symbol: str) -> InlineKeyboardMarkup:
    url = f"{settings.WEBAPP_BASE}/webapp/depth?symbol={symbol.upper()}"
    heatmap_url = f"{settings.WEBAPP_BASE}/webapp/heatmap"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📊 {symbol.upper()} CANLI 10 Kademe Derinlik",
                    web_app=WebAppInfo(url=url),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📸 Snapshot Al",
                    callback_data=f"snap|{symbol.upper()}|mobile|2",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔥 Sıcaklık Haritası",
                    web_app=WebAppInfo(url=heatmap_url),
                )
            ],
        ]
    )


def akd_keyboard(symbol: str) -> InlineKeyboardMarkup:
    url = f"{settings.WEBAPP_BASE}/webapp/akd?symbol={symbol.upper()}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🏦 {symbol.upper()} AKD (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def takas_keyboard(symbol: str) -> InlineKeyboardMarkup:
    url = f"{settings.WEBAPP_BASE}/webapp/takas?symbol={symbol.upper()}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📑 {symbol.upper()} Takas (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


def snapshot_keyboard(symbol: str) -> InlineKeyboardMarkup:
    sym = symbol.upper()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Mobil", callback_data=f"snap|{sym}|mobile|2"
                ),
                InlineKeyboardButton(
                    text="🖥️ Geniş", callback_data=f"snap|{sym}|wide|2"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Mobil (x3)", callback_data=f"snap|{sym}|mobile|3"
                ),
            ],
        ]
    )

def heatmap_keyboard() -> InlineKeyboardMarkup:
    url = f"{settings.WEBAPP_BASE}/webapp/heatmap"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 Sıcaklık Haritası (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )

# -------------------- Utilities -------------------- #


def _clean_symbol(txt: str) -> str:
    import re

    s = (txt or "").upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


# -------------------- Snapshot callback -------------------- #


@dp.callback_query(F.data.startswith("snap|"))
async def on_snap(cq: CallbackQuery):
    try:
        _, sym, size, scale = (cq.data or "").split("|", 3)
        await cq.answer("Hazırlanıyor…")

        # API üzerinden PNG (stateless, pratik)
        api = settings.API_BASE.rstrip("/")
        url = (
            f"{api}/api/snapshot/depth.png?symbol={sym}&size={size}&scale={int(scale)}"
        )
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.get(url)
        if r.status_code != 200 or not r.content:
            await cq.answer("Snapshot alınamadı.", show_alert=True)
            return
        file = BufferedInputFile(r.content, filename=f"{sym}_{size}.png")
        await bot.send_photo(
            chat_id=cq.message.chat.id, photo=file, caption=f"{sym} • {size} snapshot"
        )
    except Exception as e:
        log.exception("snapshot error: %s", e)
        await cq.answer("Snapshot alınamadı, lütfen tekrar deneyin.", show_alert=True)


# -------------------- Commands -------------------- #


@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "Merhaba! /derinlik <SEMBOL> ile canlı 10 kademe derinliği, "
        "/akd <SEMBOL> ile AKD’yi, /takas <SEMBOL> ile Takas ekranını açabilirsin.\n"
        "/sicaklikharitasi ile Sıcaklık Haritasını, /akd <SEMBOL> ile AKD’yi, "
        "/takas <SEMBOL> ile Takas ekranını açabilirsin.\n"
        "Örn: /derinlik ASTOR"
    )


@dp.message(Command("snapshot"))
async def cmd_snapshot(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /snapshot <SEMBOL>\nÖrn: /snapshot ASTOR")
    symbol = _clean_symbol(parts[1])
    await msg.answer(
        f"{symbol} için anlık görüntü boyutu seç:",
        reply_markup=snapshot_keyboard(symbol),
    )


@dp.message(Command("derinlik"))
async def cmd_depth(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /derinlik <SEMBOL>\nÖrn: /derinlik ASTOR")
    symbol = _clean_symbol(parts[1])
    await msg.answer(
        f"{symbol} CANLI Derinlik Mini Uygulamasını Açmak İçin Aşağıya Tıkla:",
        reply_markup=depth_keyboard(symbol),
    )


@dp.message(Command("akd"))
async def cmd_akd(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /akd <SEMBOL>\nÖrn: /akd ASELS")
    symbol = _clean_symbol(parts[1])
    await msg.answer(
        f"{symbol} AKD Mini Uygulamasını Aç:",
        reply_markup=akd_keyboard(symbol),
    )


@dp.message(Command("takas"))
async def cmd_takas(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /takas <SEMBOL>\nÖrn: /takas ASTOR")
    symbol = _clean_symbol(parts[1])
    await msg.answer(
        f"{symbol} Takas Mini Uygulamasını Aç:",
        reply_markup=takas_keyboard(symbol),
    )

@dp.message(Command(commands=("sicaklikharitasi", "heatmap")))
async def cmd_heatmap(msg: Message):
    await msg.answer(
        "Genel Piyasa Sıcaklık Haritasını Aç:",
        reply_markup=heatmap_keyboard(),
    )

# “snapshot al” serbest metin:
@router.message(F.text.regexp(r"(?i)\b(snapshot al|snap al|ss al)\b"))
async def cmd_snapshot_free(message: Message):
    words = (message.text or "").split()
    sym = None
    for w in words:
        w2 = _clean_symbol(w)
        if 3 <= len(w2) <= 6:
            sym = w2
            break
    if not sym:
        await message.answer(
            "Hangi sembol için? Örnek: `ASTOR snapshot al`", parse_mode="Markdown"
        )
        return
    # Basit geniş PNG:
    api = settings.API_BASE.rstrip("/")
    url = f"{api}/api/snapshot/depth.png?symbol={sym}&size=wide&scale=2"
    try:
        async with httpx.AsyncClient(timeout=20.0) as cli:
            r = await cli.get(url)
        if r.status_code != 200 or not r.content:
            await message.answer("Snapshot alınamadı, tekrar dener misin?")
            return
        photo = BufferedInputFile(r.content, filename=f"{sym}_snapshot.png")
        await message.answer_photo(photo, caption=f"{sym} • snapshot")
    except Exception:
        await message.answer("Snapshot sırasında bir hata oldu.")


# -------------------- Webhook bridge -------------------- #


def setup_webhook_app(app: FastAPI):
    @app.post(settings.WEBHOOK_RELATIVE_PATH)
    async def telegram_webhook(request: Request):
        data = await request.json()
        update = Update.model_validate(data)  # pydantic v2
        await dp.feed_webhook_update(bot, update)
        return Response(status_code=200)


async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=f"{settings.API_BASE}{settings.WEBHOOK_RELATIVE_PATH}",
        secret_token=settings.WEBHOOK_SECRET,
    )


async def on_shutdown():
    await bot.session.close()


def pgc_keyboard():
    url = f"{settings.WEBAPP_BASE}/webapp/pgc"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💸 Para Giriş-Çıkış (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


@dp.message(Command("pgc"))
async def cmd_pgc(msg: Message):
    await msg.answer(
        "Genel Para Giriş-Çıkış Mini Uygulamasını Aç:",
        reply_markup=pgc_keyboard(),
    )
