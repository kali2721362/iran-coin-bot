import os
import random
import logging
from datetime import datetime
from typing import Optional
import asyncpg
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend")

app = FastAPI(title="IRAN Coin Backend")

# اصلاح مشکل CORS (غیرفعال کردن allow_credentials جهت پذیرش * توسط مرورگر تلگرام)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
OFFERWALL_POSTBACK_SECRET = os.getenv("OFFERWALL_POSTBACK_SECRET", "")
OFFERWALL_URL_TEMPLATE = os.getenv(
    "OFFERWALL_URL_TEMPLATE",
    "https://offerwall.cpx-research.com/index.php?app_id=XXXX&ext_user_id={telegram_id}"
)
OFFERWALL_PAYOUT_TO_IRAN = float(os.getenv("OFFERWALL_PAYOUT_TO_IRAN", "1000.0"))

db_pool: Optional[asyncpg.Pool] = None

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

async def db_exec(query, *args):
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"db_exec error: {e}")
    return None

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

@app.get("/api/v1/tasks/{telegram_id}")
async def get_tasks(telegram_id: int):
    tasks = [
        {"id": 1, "title": "Join Telegram Channel", "reward": 50, "completed": False, "task_url": "https://t.me/Telegram"},
        {"id": 2, "title": "Follow Twitter", "reward": 100, "completed": False, "task_url": "https://x.com"}
    ]
    return {"success": True, "tasks": tasks}

class TaskPayload(BaseModel):
    telegram_id: int
    task_id: int

@app.post("/api/v1/tasks/complete")
async def complete_task(payload: TaskPayload):
    reward = 50.0
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

class WithdrawPayload(BaseModel):
    telegram_id: int
    amount: float
    ton_address: str

@app.post("/api/v1/withdraw/request")
async def request_withdraw(payload: WithdrawPayload):
    return {"success": True, "message": "Withdraw request submitted", "new_balance": 0.0}
