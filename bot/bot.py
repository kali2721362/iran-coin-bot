import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing (set it in Railway Variables, not in code).")
if not MINI_APP_URL:
    raise RuntimeError("MINI_APP_URL is missing (set Netlify URL in Railway Variables).")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: types.Message):
    ref = None
    if m.text and len(m.text.split()) > 1:
        ref = m.text.split()[1]

    url = MINI_APP_URL
    if ref:
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}ref={ref}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open IRAN Coin", web_app=WebAppInfo(url=url))]
    ])

    await m.answer(
        "🇮🇷 <b>Welcome to IRAN Coin!</b>\n\n"
        "Earn by watching ads, completing tasks, and inviting friends.\n"
        "Withdraw to your TON wallet inside the Mini App.",
        reply_markup=kb
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
from aiogram.client.default import DefaultBotProperties