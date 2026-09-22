import os
import asyncio
import logging
import httpx
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

load_dotenv()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
API_URL = "https://iran-coin-bot-production.up.railway.app/api/v1"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not MINI_APP_URL:
    raise RuntimeError("MINI_APP_URL is missing")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: types.Message):
    user_id = m.from_user.id
    ref = None

    if m.text and len(m.text.split()) > 1:
        raw_ref = m.text.split()[1]
        if raw_ref.startswith("ref_"):
            ref = raw_ref.replace("ref_", "").strip()
        else:
            ref = raw_ref.strip()

        if ref == str(user_id):
            ref = None

    url = MINI_APP_URL
    if ref:
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}ref={ref}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open IRAN Coin", web_app=WebAppInfo(url=url))]
    ])

    await m.answer(
        "🇮🇷 <b>Welcome to IRAN Coin!</b>\n\n"
        "Earn by watching ads, completing tasks, daily lucky spin, and inviting friends.\n"
        "Withdraw to your TON wallet inside the Mini App.",
        reply_markup=kb
    )

# --- پنل ادمین برای مدیریت ---
@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        return

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{API_URL}/admin/stats")
            data = res.json()

        text = (
            "📊 <b>پنل مدیریت اختصاصی IRAN Coin</b>\n\n"
            f"👥 تعداد کل کاربران: <b>{data.get('total_users', 0)} نفر</b>\n"
            f"💰 کل سکه‌های در گردشک: <b>{data.get('total_balance', 0):,.0f} IRAN</b>\n"
            f"⏳ درخواست‌های برداشت در انتظار: <b>{data.get('pending_withdrawals', 0)} عدد</b>"
        )
        await m.answer(text)
    except Exception as e:
        await m.answer(f"خطا در دریافت آمار: {e}")

# --- کلیک ادمین روی دکمه‌های تایید یا رد برداشت ---
@dp.callback_query(F.data.startswith("wd_"))
async def handle_withdraw_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("دسترسی غیرمجاز", show_alert=True)

    data = call.data.split("_")
    action = data[1] # approve or reject
    wd_id = data[2]
    user_id = data[3]

    if action == "approve":
        await call.message.edit_text(call.message.text + "\n\n✅ <b>این درخواست تایید و واریز شد.</b>")
        try:
            await bot.send_message(user_id, "🎉 <b>درخواست برداشت شما با موفقیت تایید و به کیف پول TON شما واریز شد!</b>")
        except:
            pass
        await call.answer("تایید شد!")

    elif action == "reject":
        refund_amount = float(data[4]) if len(data) > 4 else 0.0
        # عودت سکه به کاربر
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{API_URL}/ads/watch", json={"telegram_id": int(user_id), "ad_id": 0})
        except:
            pass

        await call.message.edit_text(call.message.text + "\n\n❌ <b>این درخواست رد شد و سکه‌ها عودت داده شد.</b>")
        try:
            await bot.send_message(user_id, f"❌ درخواست برداشت شما رد شد و {refund_amount} سکه به حساب شما بازگشت.")
        except:
            pass
        await call.answer("رد شد!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
