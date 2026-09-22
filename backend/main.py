import os
import random
import logging
import json
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

DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "979411415")
OFFERWALL_POSTBACK_SECRET = os.getenv("OFFERWALL_POSTBACK_SECRET", "")
OFFERWALL_URL_TEMPLATE = os.getenv(
    "OFFERWALL_URL_TEMPLATE",
    "https://offerwall.cpx-research.com/index.php?app_id=XXXX&ext_user_id={telegram_id}"
)
OFFERWALL_PAYOUT_TO_IRAN = float(os.getenv("OFFERWALL_PAYOUT_TO_IRAN", "1000.0"))

db_pool: Optional[asyncpg.Pool] = None

REAL_TASKS = [
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
                
                # جدول برداشت‌ها
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
            except Exception as e:
                logger.warning(f"Note on DB Migration: {e}")
        except Exception as e:
            logger.error(f"❌ Database Connection Error: {e}")

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

def send_telegram_msg(chat_id: str, text: str, reply_markup: dict = None):
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.error(f"Telegram notify error: {e}")

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
                    send_telegram_msg(possible_ref, f"🎉 <b>کاربر جدیدی با لینک شما وارد شد!</b>\n🎁 ۵۰۰ سکه به شما تعلق گرفت.")
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

    task_list = []
    for t in REAL_TASKS:
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
    task = next((t for t in REAL_TASKS if t["id"] == payload.task_id), None)

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

# --- درخواست برداشت سیستم همراه با سیستم اطلاع‌رسانی آنی به ادمین ---
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

    # ثبت در دیتابیس
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

    # ارسال هشدار آنی برای ادمین در تلگرام با دکمه واریز
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
    send_telegram_msg(ADMIN_ID, msg, markup)

    return {"success": True, "message": "درخواست برداشت ثبت شد و برای ادمین ارسال گردید.", "new_balance": new_bal}

# --- آمار کامل پنل ادمین ---
@app.get("/api/v1/admin/stats")
async def get_admin_stats():
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

    return {
        "total_users": total_users,
        "total_balance": total_balance,
        "pending_withdrawals": pending_wd
    }

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
