# app/bot.py
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Update
)
from fastapi import FastAPI, Request
from starlette.responses import Response
from .config import settings

log = logging.getLogger("bot")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

def depth_keyboard(symbol: str):
    url = f"{settings.WEBAPP_BASE}/webapp/depth?symbol={symbol.upper()}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"📊 {symbol.upper()} Derinlik (Mini App)", web_app=WebAppInfo(url=url))
    ]])
    return kb

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "Merhaba! /derinlik <SEMBOL> ile canlı 10 kademe derinliği açabilirsin.\nÖrn: /derinlik ASTOR"
    )

@dp.message(Command("derinlik"))
async def cmd_depth(msg: Message):
    parts = (msg.text or "").split()
    if len(parts) < 2:
        return await msg.reply("Kullanım: /derinlik <SEMBOL>\nÖrn: /derinlik ASTOR")
    symbol = parts[1].strip().upper()
    await msg.answer(
        f"{symbol} derinlik mini uygulamasını açmak için aşağıya tıkla:",
        reply_markup=depth_keyboard(symbol)
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
        secret_token=settings.WEBHOOK_SECRET
    )

async def on_shutdown():
    await bot.session.close()
