import os
import json
import random
import logging
import urllib.request
from datetime import datetime
from typing import Optional
import asyncpg
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app = FastAPI(title="IRAN Coin Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# متغیرهای محیطی
DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://loquacious-frangollo-386374.netlify.app")
ADMIN_ID = str(os.getenv("ADMIN_ID", "979411415")).strip()
SERVER_URL = "https://iran-coin-bot-production.up.railway.app"

OFFERWALL_POSTBACK_SECRET = os.getenv("OFFERWALL_POSTBACK_SECRET", "")
OFFERWALL_URL_TEMPLATE = os.getenv(
    "OFFERWALL_URL_TEMPLATE",
    "https://offerwall.cpx-research.com/index.php?app_id=XXXX&ext_user_id={telegram_id}"
)
OFFERWALL_PAYOUT_TO_IRAN = float(os.getenv("OFFERWALL_PAYOUT_TO_IRAN", "1000.0"))

db_pool: Optional[asyncpg.Pool] = None

# تسک‌های پیش‌فرض
DEFAULT_TASKS = [
    {
        "id": 1,
        "title": "عضویت در کانال رسمی",
        "reward": 100,
        "chat_id": "@IRANCoinChannel",
        "task_url": "https://t.me/IRANCoinChannel"
    },
    {
        "id": 2,
        "title": "عضویت در گروه چت",
        "reward": 100,
        "chat_id": "@IRANCoinGroup",
        "task_url": "https://t.me/IRANCoinGroup"
    }
]

def send_telegram_api(method: str, payload: dict):
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Telegram API Error ({method}): {e}")
        return None

# --------------------------------------------------
# مدیریت دیتابیس
# --------------------------------------------------
@app.on_event("startup")
async def startup():
    global db_pool
    if DATABASE_URL:
        try:
            dsn = DATABASE_URL.replace("postgres://", "postgresql://", 1)
            db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
            logger.info("✅ Database Pool Connected!")
            
            try:
                await db_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_spin TEXT;")
                await db_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by TEXT;")
                await db_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS completed_tasks TEXT;")
                await db_exec("""
                    CREATE TABLE IF NOT EXISTS withdrawals (
                        id SERIAL PRIMARY KEY,
                        telegram_id BIGINT NOT NULL,
                        amount FLOAT NOT NULL,
                        ton_address TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                await db_exec("""
                    CREATE TABLE IF NOT EXISTS custom_tasks (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        reward FLOAT NOT NULL,
                        chat_id TEXT NOT NULL,
                        task_url TEXT NOT NULL
                    );
                """)
            except Exception as e:
                logger.warning(f"Note on DB Migration: {e}")
        except Exception as e:
            logger.error(f"❌ Database Connection Error: {e}")

    if BOT_TOKEN:
        webhook_url = f"{SERVER_URL}/api/v1/telegram/webhook"
        send_telegram_api("setWebhook", {"url": webhook_url})

@app.on_event("shutdown")
async def shutdown():
    global db_pool
    if db_pool:
        await db_pool.close()

async def db_fetchrow(query, *args):
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"db_fetchrow error: {e}")
    return None

async def db_fetch(query, *args):
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"db_fetch error: {e}")
    return []

async def db_exec(query, *args):
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"db_exec error: {e}")
    return None

def check_telegram_membership_sync(chat_id: str, user_id: int) -> bool:
    if not BOT_TOKEN or not chat_id:
        return True
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={chat_id}&user_id={user_id}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                status = data.get("result", {}).get("status", "")
                return status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
    return False

# --------------------------------------------------
# Webhook تلگرام (دستورات Start, Admin, Broadcast, AddTask)
# --------------------------------------------------
@app.post("/api/v1/telegram/webhook")
async def telegram_webhook(request: Request):
    try:
        update = await request.json()
    except Exception:
        return {"status": "ok"}

    if "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id")
        user_id = str(msg.get("from", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if text.startswith("/start"):
            ref = None
            parts = text.split()
            if len(parts) > 1:
                raw_ref = parts[1]
                if raw_ref.startswith("ref_"):
                    ref = raw_ref.replace("ref_", "").strip()
                else:
                    ref = raw_ref.strip()
                if ref == user_id:
                    ref = None

            app_url = MINI_APP_URL
            if ref:
                joiner = "&" if "?" in app_url else "?"
                app_url = f"{app_url}{joiner}ref={ref}"

            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🚀 Open IRAN Coin", "web_app": {"url": app_url}}]
                ]
            }

            welcome_text = (
                "🇮🇷 <b>Welcome to IRAN Coin!</b>\n\n"
                "Earn by watching ads, completing tasks, daily lucky spin, and inviting friends.\n"
                "Withdraw to your TON wallet inside the Mini App."
            )
            send_telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup
            })

        # --- پنل ادمین ---
        elif text == "/admin":
            if user_id != ADMIN_ID:
                send_telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"❌ شما ادمین نیستید.\nآیدی شما: <code>{user_id}</code>",
                    "parse_mode": "HTML"
                })
            else:
                total_users = 0
                total_balance = 0.0
                pending_wd = 0

                if db_pool:
                    try:
                        u_row = await db_fetchrow("SELECT COUNT(*) as count, SUM(balance) as total FROM users;")
                        if u_row:
                            total_users = int(u_row.get("count") or 0)
                            total_balance = float(u_row.get("total") or 0.0)

                        w_row = await db_fetchrow("SELECT COUNT(*) as count FROM withdrawals WHERE status='pending';")
                        if w_row:
                            pending_wd = int(w_row.get("count") or 0)
                    except Exception as e:
                        logger.error(f"Admin stats error: {e}")

                admin_text = (
                    "📊 <b>پنل مدیریت اختصاصی IRAN Coin</b>\n\n"
                    f"👥 تعداد کل کاربران: <b>{total_users} نفر</b>\n"
                    f"💰 کل سکه‌های در گردش: <b>{total_balance:,.0f} IRAN</b>\n"
                    f"⏳ درخواست‌های برداشت در انتظار: <b>{pending_wd} عدد</b>\n\n"
                    "📌 <b>دستورات ادمین:</b>\n"
                    "<code>/broadcast متن_پیام</code> - ارسال پیام همگانی\n"
                    "<code>/addtask @آیدی_کانال ۱۰۰ عنوان لینک</code> - افزودن تسک اسپانسری"
                )
                send_telegram_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": admin_text,
                    "parse_mode": "HTML"
                })

        # --- ارسال پیام همگانی (Broadcast) ---
        elif text.startswith("/broadcast "):
            if user_id == ADMIN_ID:
                bc_text = text.replace("/broadcast ", "").strip()
                if bc_text and db_pool:
                    users = await db_fetch("SELECT telegram_id FROM users;")
                    sent_count = 0
                    for u in users:
                        tid = u.get("telegram_id")
                        if tid:
                            res = send_telegram_api("sendMessage", {
                                "chat_id": str(tid),
                                "text": bc_text,
                                "parse_mode": "HTML"
                            })
                            if res and res.get("ok"):
                                sent_count += 1
                    send_telegram_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"✅ پیام همگانی با موفقیت به <b>{sent_count}</b> کاربر ارسال شد.",
                        "parse_mode": "HTML"
                    })

        # --- افزودن تسک اسپانسری متحرک ---
        elif text.startswith("/addtask "):
            if user_id == ADMIN_ID:
                try:
                    parts = text.split(maxsplit=4)
                    # فرمت: /addtask @channel 100 عنوان_تسک https://t.me/channel
                    chat_target = parts[1]
                    reward_val = float(parts[2])
                    task_title = parts[3]
                    task_url = parts[4]

                    if db_pool:
                        await db_exec("""
                            INSERT INTO custom_tasks(title, reward, chat_id, task_url)
                            VALUES($1, $2, $3, $4);
                        """, task_title, reward_val, chat_target, task_url)
                        send_telegram_api("sendMessage", {
                            "chat_id": chat_id,
                            "text": f"✅ تسک جدید با موفقیت اضافه شد:\n<b>{task_title}</b> (+{reward_val} سکه)",
                            "parse_mode": "HTML"
                        })
                except Exception as e:
                    send_telegram_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"❌ فرمت دستور نادرست است.\nفرمت صحیح:\n<code>/addtask @Channel 100 عنوان لینک</code>",
                        "parse_mode": "HTML"
                    })

    # دکمه‌های تایید/رد برداشت
    elif "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb.get("id")
        user_id = str(cb.get("from", {}).get("id", ""))
        data = cb.get("data", "")
        msg = cb.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")
        old_text = msg.get("text", "")

        if data.startswith("wd_"):
            if user_id != ADMIN_ID:
                send_telegram_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "دسترسی غیرمجاز", "show_alert": True})
                return {"status": "ok"}

            parts = data.split("_")
            action = parts[1]
            wd_id = parts[2]
            target_user_id = parts[3]

            if action == "approve":
                await db_exec("UPDATE withdrawals SET status='approved' WHERE id=$1;", int(wd_id))
                send_telegram_api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": old_text + "\n\n✅ <b>این درخواست تایید و واریز شد.</b>",
                    "parse_mode": "HTML"
                })
                send_telegram_api("sendMessage", {
                    "chat_id": target_user_id,
                    "text": "🎉 <b>درخواست برداشت شما با موفقیت تایید و به کیف پول TON شما واریز شد!</b>",
                    "parse_mode": "HTML"
                })
                send_telegram_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "تایید شد!"})

            elif action == "reject":
                refund_amount = float(parts[4]) if len(parts) > 4 else 0.0
                await db_exec("UPDATE withdrawals SET status='rejected' WHERE id=$1;", int(wd_id))
                await db_exec("UPDATE users SET balance = balance + $1 WHERE telegram_id::text=$2;", refund_amount, str(target_user_id))
                send_telegram_api("editMessageText", {
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": old_text + "\n\n❌ <b>این درخواست رد شد و سکه‌ها عودت داده شد.</b>",
                    "parse_mode": "HTML"
                })
                send_telegram_api("sendMessage", {
                    "chat_id": target_user_id,
                    "text": f"❌ درخواست برداشت شما رد شد و {refund_amount} سکه به حساب شما بازگشت.",
                    "parse_mode": "HTML"
                })
                send_telegram_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "رد شد!"})

    return {"status": "ok"}

SPIN_REWARDS_LIST = [
    {"index": 0, "amount": 10,  "label": "10",  "chance": 500},
    {"index": 1, "amount": 20,  "label": "20",  "chance": 300},
    {"index": 2, "amount": 50,  "label": "50",  "chance": 120},
    {"index": 3, "amount": 100, "label": "100", "chance": 50},
    {"index": 4, "amount": 200, "label": "200", "chance": 25},
    {"index": 5, "amount": 500, "label": "500", "chance": 5},
]

@app.get("/")
async def root():
    return {"status": "ok", "message": "IRAN Coin Backend is running!"}

class InitPayload(BaseModel):
    initData: Optional[str] = ""
    user: dict
    ref: Optional[str] = None

@app.post("/api/v1/user/init")
async def init_user(payload: InitPayload):
    u = payload.user
    tg_id = int(u.get("id", 0))
    username = u.get("username", "")
    first_name = u.get("first_name", "User")
    ref = payload.ref

    if not tg_id:
        raise HTTPException(400, "Invalid user")

    user_row = await db_fetchrow("SELECT * FROM users WHERE telegram_id::text=$1;", str(tg_id))

    if not user_row:
        referred_by = None
        if ref and ref.startswith("ref_"):
            try:
                possible_ref = str(ref.replace("ref_", "").strip())
                if possible_ref != str(tg_id):
                    referred_by = possible_ref
                    await db_exec("UPDATE users SET balance = balance + 500 WHERE telegram_id::text=$1;", possible_ref)
                    send_telegram_api("sendMessage", {
                        "chat_id": possible_ref,
                        "text": "🎉 <b>کاربر جدیدی با لینک شما وارد شد!</b>\n🎁 ۵۰۰ سکه پاداش گرفتید.",
                        "parse_mode": "HTML"
                    })
            except:
                pass

        await db_exec("""
            INSERT INTO users(telegram_id, username, first_name, balance, referred_by, referral_code)
            VALUES($1, $2, $3, 0.0, $4, $5) ON CONFLICT DO NOTHING;
        """, tg_id, username, first_name, referred_by, str(tg_id))

        user_row = await db_fetchrow("SELECT * FROM users WHERE telegram_id::text=$1;", str(tg_id))

    balance = float(user_row.get("balance", 0.0)) if user_row else 0.0

    return {
        "success": True,
        "user": {
            "telegram_id": tg_id,
            "username": username,
            "first_name": first_name,
            "balance": balance,
            "referral_code": str(tg_id)
        }
    }

@app.get("/api/v1/user/stats/{telegram_id}")
async def get_user_stats(telegram_id: str):
    tg_str = str(telegram_id).strip()
    coins = 0.0
    ref_count = 0
    last_spin_str = None

    if db_pool:
        try:
            row = await db_fetchrow("SELECT balance, last_spin FROM users WHERE telegram_id::text=$1;", tg_str)
            if row:
                coins = float(row.get("balance") or 0.0)
                last_spin_str = row.get("last_spin")
        except Exception:
            pass

        try:
            ref_row = await db_fetchrow("SELECT COUNT(*) as count FROM users WHERE referred_by=$1;", tg_str)
            if ref_row:
                ref_count = int(ref_row.get("count") or 0)
        except Exception:
            pass

    can_spin = True
    seconds_left = 0

    if last_spin_str:
        try:
            if isinstance(last_spin_str, str):
                last_spin = datetime.fromisoformat(last_spin_str)
            else:
                last_spin = last_spin_str
            diff = (datetime.utcnow() - last_spin).total_seconds()
            if diff < 86400:
                can_spin = False
                seconds_left = int(86400 - diff)
        except Exception:
            pass

    return {
        "telegram_id": telegram_id,
        "coins": coins,
        "referrals_count": ref_count,
        "can_spin": can_spin,
        "seconds_to_next_spin": seconds_left
    }

@app.post("/api/v1/spin/{telegram_id}")
async def process_spin(telegram_id: str):
    tg_str = str(telegram_id).strip()
    coins = 0.0
    last_spin_str = None

    if db_pool:
        try:
            row = await db_fetchrow("SELECT balance, last_spin FROM users WHERE telegram_id::text=$1;", tg_str)
            if row:
                coins = float(row.get("balance") or 0.0)
                last_spin_str = row.get("last_spin")
        except Exception:
            pass

    if last_spin_str:
        try:
            if isinstance(last_spin_str, str):
                last_spin = datetime.fromisoformat(last_spin_str)
            else:
                last_spin = last_spin_str
            if (datetime.utcnow() - last_spin).total_seconds() < 86400:
                raise HTTPException(status_code=400, detail="باید ۲۴ ساعت از چرخش قبلی بگذرد.")
        except HTTPException as e:
            raise e
        except Exception:
            pass

    weights = [r["chance"] for r in SPIN_REWARDS_LIST]
    chosen = random.choices(SPIN_REWARDS_LIST, weights=weights, k=1)[0]
    reward_amount = float(chosen["amount"])
    new_coins = coins + reward_amount
    now_iso = datetime.utcnow().isoformat()

    if db_pool:
        try:
            await db_exec("""
                UPDATE users
                SET balance = balance + $1,
                    last_spin = $2,
                    updated_at = now()
                WHERE telegram_id::text=$3;
            """, reward_amount, now_iso, tg_str)
        except Exception as e:
            logger.error(f"Error updating spin: {e}")

    return {
        "success": True,
        "reward_index": chosen["index"],
        "reward_amount": chosen["amount"],
        "new_balance": new_coins
    }

# --- ترکیبی از تسک‌های اصلی + تسک‌های اسپانسری افزوده شده ---
@app.get("/api/v1/tasks/{telegram_id}")
async def get_tasks(telegram_id: str):
    tg_str = str(telegram_id).strip()
    completed_ids = []
    if db_pool:
        try:
            row = await db_fetchrow("SELECT completed_tasks FROM users WHERE telegram_id::text=$1;", tg_str)
            if row and row.get("completed_tasks"):
                completed_ids = [int(x) for x in str(row["completed_tasks"]).split(",") if x.strip()]
        except Exception:
            pass

    all_tasks = list(DEFAULT_TASKS)

    if db_pool:
        try:
            c_rows = await db_fetch("SELECT * FROM custom_tasks;")
            for cr in c_rows:
                all_tasks.append({
                    "id": int(cr["id"]) + 100, # شناسه مجزا برای تسک‌های سفارشی
                    "title": cr["title"],
                    "reward": float(cr["reward"]),
                    "chat_id": cr["chat_id"],
                    "task_url": cr["task_url"]
                })
        except Exception:
            pass

    task_list = []
    for t in all_tasks:
        task_list.append({
            "id": t["id"],
            "title": t["title"],
            "reward": t["reward"],
            "completed": t["id"] in completed_ids,
            "task_url": t["task_url"]
        })

    return {"success": True, "tasks": task_list}

class TaskPayload(BaseModel):
    telegram_id: int
    task_id: int

@app.post("/api/v1/tasks/complete")
async def complete_task(payload: TaskPayload):
    tg_str = str(payload.telegram_id)

    all_tasks = list(DEFAULT_TASKS)
    if db_pool:
        try:
            c_rows = await db_fetch("SELECT * FROM custom_tasks;")
            for cr in c_rows:
                all_tasks.append({
                    "id": int(cr["id"]) + 100,
                    "title": cr["title"],
                    "reward": float(cr["reward"]),
                    "chat_id": cr["chat_id"],
                    "task_url": cr["task_url"]
                })
        except Exception:
            pass

    task = next((t for t in all_tasks if t["id"] == payload.task_id), None)

    if not task:
        raise HTTPException(400, "تسک یافت نشد")

    is_member = check_telegram_membership_sync(task["chat_id"], payload.telegram_id)
    if not is_member:
        return {"success": False, "message": "ابتدا باید عضو کانال/گروه شوید!"}

    reward = float(task["reward"])
    new_bal = 0.0

    if db_pool:
        try:
            row = await db_fetchrow("SELECT completed_tasks, balance FROM users WHERE telegram_id::text=$1;", tg_str)
            completed_str = row.get("completed_tasks") or "" if row else ""
            completed_list = [int(x) for x in completed_str.split(",") if x.strip()]

            if payload.task_id in completed_list:
                return {"success": False, "message": "این تسک قبلاً انجام شده است."}

            completed_list.append(payload.task_id)
            new_completed_str = ",".join(map(str, completed_list))

            await db_exec("""
                UPDATE users 
                SET balance = balance + $1, 
                    completed_tasks = $2 
                WHERE telegram_id::text=$3;
            """, reward, new_completed_str, tg_str)

            updated_row = await db_fetchrow("SELECT balance FROM users WHERE telegram_id::text=$1;", tg_str)
            new_bal = float(updated_row.get("balance", 0.0)) if updated_row else reward
        except Exception as e:
            logger.error(f"Task error: {e}")

    return {"success": True, "reward": reward, "new_balance": new_bal}

class WithdrawPayload(BaseModel):
    telegram_id: int
    amount: float
    ton_address: str

@app.post("/api/v1/withdraw/request")
async def request_withdraw(payload: WithdrawPayload):
    tg_str = str(payload.telegram_id)
    amount = float(payload.amount)
    addr = payload.ton_address.strip()

    if amount < 500:
        return {"success": False, "message": "حداقل میزان برداشت ۵۰۰ سکه است."}

    user = await db_fetchrow("SELECT balance FROM users WHERE telegram_id::text=$1;", tg_str)
    curr_bal = float(user.get("balance", 0.0)) if user else 0.0

    if curr_bal < amount:
        return {"success": False, "message": "موجودی شما کافی نیست."}

    new_bal = curr_bal - amount
    await db_exec("UPDATE users SET balance=$1 WHERE telegram_id::text=$2;", new_bal, tg_str)

    wd_id = 1
    if db_pool:
        try:
            row = await db_fetchrow("""
                INSERT INTO withdrawals(telegram_id, amount, ton_address, status)
                VALUES($1, $2, $3, 'pending') RETURNING id;
            """, payload.telegram_id, amount, addr)
            if row:
                wd_id = row.get("id")
        except Exception as e:
            logger.error(f"Withdraw insert error: {e}")

    msg = (
        f"🚨 <b>درخواست برداشت جدید!</b>\n\n"
        f"👤 کاربر: <code>{payload.telegram_id}</code>\n"
        f"💰 مقدار: <b>{amount} IRAN</b>\n"
        f"👛 آدرس ولت:\n<code>{addr}</code>"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ تایید و واریز شد", "callback_data": f"wd_approve_{wd_id}_{payload.telegram_id}"},
                {"text": "❌ رد درخواست", "callback_data": f"wd_reject_{wd_id}_{payload.telegram_id}_{amount}"}
            ]
        ]
    }
    send_telegram_api("sendMessage", {
        "chat_id": ADMIN_ID,
        "text": msg,
        "parse_mode": "HTML",
        "reply_markup": markup
    })

    return {"success": True, "message": "درخواست برداشت ثبت شد.", "new_balance": new_bal}

@app.get("/api/v1/offerwall/link/{user_id}")
async def get_offerwall_link(user_id: str):
    url = OFFERWALL_URL_TEMPLATE.replace("{telegram_id}", str(user_id))
    return {"success": True, "url": url}

@app.api_route("/api/v1/offerwall/postback", methods=["GET", "POST"])
async def offerwall_postback(
    request: Request,
    x_postback_secret: Optional[str] = Header(default=None),
):
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        try:
            params = await request.json()
        except:
            params = dict(request.query_params)

    secret = (params.get("secret") or x_postback_secret or "").strip()
    if OFFERWALL_POSTBACK_SECRET and secret != OFFERWALL_POSTBACK_SECRET:
        raise HTTPException(401, "Invalid secret")

    event_id = str(
        params.get("event_id") or params.get("trans_id") or params.get("click_id") or ""
    ).strip()
    if not event_id:
        raise HTTPException(400, "event_id required")

    telegram_id = str(
        params.get("telegram_id") or params.get("user_id") or params.get("sub_id") or "0"
    )

    payout = float(params.get("amount_usd") or params.get("payout") or 0)
    reward_iran = max(0.0, payout * OFFERWALL_PAYOUT_TO_IRAN)

    await db_exec("UPDATE users SET balance = balance + $1 WHERE telegram_id::text=$2;", reward_iran, telegram_id)

    return {"status": "ok", "telegram_id": telegram_id, "reward_iran": reward_iran}

class AdPayload(BaseModel):
    telegram_id: int
    ad_id: int

@app.post("/api/v1/ads/watch")
async def watch_ad(payload: AdPayload):
    reward = 20.0
    await db_exec("UPDATE users SET balance = balance + $1 WHERE telegram_id::text=$2;", reward, str(payload.telegram_id))
    row = await db_fetchrow("SELECT balance FROM users WHERE telegram_id::text=$1;", str(payload.telegram_id))
    new_bal = float(row.get("balance", 0.0)) if row else reward
    return {"success": True, "reward": reward, "new_balance": new_bal}

@app.get("/api/v1/user/{telegram_id}/transactions")
async def get_transactions(telegram_id: int):
    return {"success": True, "transactions": []}

@app.get("/api/v1/miner/status/{telegram_id}")
async def miner_status(telegram_id: int):
    return {"success": True, "active": True, "pending": 15.5, "rate_per_hour": 10.0}

@app.post("/api/v1/miner/start")
async def miner_start(payload: dict):
    return {"success": True, "message": "Mining started"}

@app.post("/api/v1/miner/claim")
async def miner_claim(payload: dict):
    return {"success": True, "claimed": 15.5, "new_balance": 100.0}
