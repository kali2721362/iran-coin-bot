import os
import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

# تنظیمات اصلی
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "")
# آیدی شما به عنوان مقدار پیش‌فرض
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
API_URL = "https://iran-coin-bot-production.up.railway.app/api/v1"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: types.Message):
    url = MINI_APP_URL
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open App", web_app=WebAppInfo(url=url))]
    ])
    await m.answer("✅ ربات آنلاین است! دکمه زیر را بزنید:", reply_markup=kb)

# --- پنل ادمین با قابلیت تشخیص خطا ---
@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    # تست ۱: آیا آیدی فرستنده با ادمین یکی است؟
    if m.from_user.id != ADMIN_ID:
        await m.answer(f"❌ شما ادمین نیستید.\nآیدی شما: <code>{m.from_user.id}</code>\nآیدی تنظیم شده ادمین: <code>{ADMIN_ID}</code>")
        return

    await m.answer("⏳ در حال دریافت آمار از سرور...")

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{API_URL}/admin/stats", timeout=10)
            if res.status_code == 200:
                data = res.json()
                text = (
                    "📊 <b>پنل مدیریت IRAN Coin</b>\n\n"
                    f"👥 کاربران: <b>{data.get('total_users', 0)}</b>\n"
                    f"💰 سکه‌های کل: <b>{data.get('total_balance', 0):,.0f}</b>\n"
                    f"⏳ برداشت‌های در انتظار: <b>{data.get('pending_withdrawals', 0)}</b>"
                )
                await m.answer(text)
            else:
                await m.answer(f"❌ خطا در سرور بک‌اند. کد خطا: {res.status_code}")
    except Exception as e:
        await m.answer(f"❌ خطای شبکه: سرور بک‌اند پاسخ نمی‌دهد.\n<code>{str(e)}</code>")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
