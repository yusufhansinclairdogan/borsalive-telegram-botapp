# app/bot.py
import io
from aiogram import F
from aiogram.types import BufferedInputFile, CallbackQuery
from .snapshot import render_depth_png
from .depth_hub import hub
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    Update,
)
from fastapi import FastAPI, Request
from starlette.responses import Response
from .config import settings

log = logging.getLogger("bot")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()


def depth_keyboard(symbol: str):
    url = f"{settings.WEBAPP_BASE}/webapp/depth?symbol={symbol.upper()}"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📊 {symbol.upper()} Derinlik (Mini App)",
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )
    return kb


def depth_keyboard(symbol: str):
    url = f"{settings.WEBAPP_BASE}/webapp/depth?symbol={symbol.upper()}"
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
        ]
    )


@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "Merhaba! /derinlik <SEMBOL> ile canlı 10 kademe derinliği açabilirsin.\nÖrn: /derinlik ASTOR"
    )


@dp.message(Command("snapshot"))
async def cmd_snapshot(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /snapshot <SEMBOL>\nÖrn: /snapshot ASTOR")
    symbol = parts[1].strip().upper()
    await msg.answer(
        f"{symbol} için anlık görüntü boyutu seç:",
        reply_markup=snapshot_keyboard(symbol),
    )


@dp.callback_query(F.data.startswith("snap|"))
async def on_snap(cq: CallbackQuery):
    try:
        _, sym, size, scale = (cq.data or "").split("|", 3)
        await cq.answer("Hazırlanıyor…")
        # Son veriyi 1 sn bekleyerek çek
        levels = await hub.get_last_levels(sym, timeout=1.0) or []
        png = render_depth_png(levels, sym, size=size, scale=int(scale))
        file = BufferedInputFile(png, filename=f"{sym}_{size}.png")
        await bot.send_photo(
            chat_id=cq.message.chat.id, photo=file, caption=f"{sym} • {size} snapshot"
        )
    except Exception as e:
        await cq.answer("Snapshot alınamadı, lütfen tekrar deneyin.", show_alert=True)
        log.exception("snapshot error: %s", e)


@dp.message(Command("derinlik"))
async def cmd_depth(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /derinlik <SEMBOL>\nÖrn: /derinlik ASTOR")
    symbol = parts[1].strip().upper()
    await msg.answer(
        f"{symbol} CANLI Derinlik Mini Uygulamasını Açmak İçin Aşağıya Tıkla:",
        reply_markup=depth_keyboard(symbol),
    )


# ---- FastAPI <-> Aiogram webhook entegrasyonu (aiogram v3 uyumlu) ----
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


def snapshot_keyboard(symbol: str):
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
