import os
import json
import random
import string
from datetime import datetime, timezone, timedelta

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

APP_TZ = timezone.utc

def now_utc():
    return datetime.now(APP_TZ)

def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except:
        return default

def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except:
        return default

AD_REWARD = env_float("AD_REWARD", 10)
AD_COOLDOWN = env_int("AD_COOLDOWN", 3600)
MAX_ADS_PER_DAY = env_int("MAX_ADS_PER_DAY", 10)

MIN_WITHDRAW = env_float("MIN_WITHDRAW", 500)
WITHDRAW_FEE = env_float("WITHDRAW_FEE", 0.05)
IRAN_TO_TON_RATE = env_float("IRAN_TO_TON_RATE", 0.000002)

REF_REWARD = env_float("REF_REWARD", 50)

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    # Railway will provide DATABASE_URL; locally you can set it
    pass

# asyncpg expects postgresql:// (not sqlalchemy's postgresql+asyncpg://)
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

app = FastAPI(title="IRAN Coin API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool: asyncpg.Pool | None = None

def gen_ref_code(n=8):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

async def db_exec(sql: str, *args):
    assert pool is not None
    async with pool.acquire() as conn:
        return await conn.execute(sql, *args)

async def db_fetchrow(sql: str, *args):
    assert pool is not None
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args)

async def db_fetch(sql: str, *args):
    assert pool is not None
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)

async def ensure_tables():
    await db_exec("""
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        balance DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_earned DOUBLE PRECISION NOT NULL DEFAULT 0,
        referral_code TEXT UNIQUE NOT NULL,
        referred_by_telegram_id BIGINT,
        referral_count INT NOT NULL DEFAULT 0,
        referral_earnings DOUBLE PRECISION NOT NULL DEFAULT 0,
        ton_wallet TEXT,
        last_ad_watch TIMESTAMPTZ,
        ads_watched_today INT NOT NULL DEFAULT 0,
        last_ad_reset DATE,
        total_ads_watched INT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    await db_exec("""
    CREATE TABLE IF NOT EXISTS transactions (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        type TEXT NOT NULL,
        amount DOUBLE PRECISION NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        ton_amount DOUBLE PRECISION,
        ton_address TEXT,
        tx_hash TEXT,
        fee DOUBLE PRECISION DEFAULT 0
    );
    """)

    await db_exec("""
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        title TEXT NOT NULL,
        reward DOUBLE PRECISION NOT NULL,
        task_type TEXT NOT NULL,
        url TEXT,
        active BOOLEAN NOT NULL DEFAULT TRUE
    );
    """)

    await db_exec("""
    CREATE TABLE IF NOT EXISTS user_tasks (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        task_id INT NOT NULL,
        completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(telegram_id, task_id)
    );
    """)

    await db_exec("""
    CREATE TABLE IF NOT EXISTS withdraw_requests (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        iran_amount DOUBLE PRECISION NOT NULL,
        ton_amount DOUBLE PRECISION NOT NULL,
        ton_address TEXT NOT NULL,
        fee DOUBLE PRECISION NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        tx_hash TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

async def seed_tasks():
    rows = await db_fetch("SELECT id FROM tasks LIMIT 1;")
    if rows:
        return
    tasks = [
        ("Join our Telegram channel", 50, "join_channel", "https://t.me/IranCoinChannel"),
        ("Follow on X (Twitter)", 50, "follow", "https://twitter.com/IranCoin"),
        ("Subscribe to YouTube", 75, "subscribe", "https://youtube.com/@IranCoin"),
        ("Join Discord", 50, "join", "https://discord.gg/IranCoin"),
        ("Complete Survey", 100, "survey", "https://irancoin.io/survey"),
    ]
    for t in tasks:
        await db_exec("INSERT INTO tasks(title, reward, task_type, url) VALUES($1,$2,$3,$4);", *t)

@app.on_event("startup")
async def startup():
    global pool
    if not DATABASE_URL:
        print("❌ DATABASE_URL is not set")
        return
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    await ensure_tables()
    await seed_tasks()
    print("✅ API started + tables ensured")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "IRAN Coin API"}

async def upsert_user(user: dict, ref: str | None):
    telegram_id = int(user["id"])
    username = user.get("username")
    first_name = user.get("first_name") or "User"
    last_name = user.get("last_name")

    row = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if row:
        await db_exec(
            "UPDATE users SET username=$1, first_name=$2, last_name=$3, updated_at=now() WHERE telegram_id=$4;",
            username, first_name, last_name, telegram_id
        )
        row = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
        return dict(row)

    # create new with unique referral_code
    ref_code = gen_ref_code()
    for _ in range(20):
        exists = await db_fetchrow("SELECT 1 FROM users WHERE referral_code=$1;", ref_code)
        if not exists:
            break
        ref_code = gen_ref_code()

    await db_exec("""
        INSERT INTO users(telegram_id, username, first_name, last_name, referral_code)
        VALUES($1,$2,$3,$4,$5);
    """, telegram_id, username, first_name, last_name, ref_code)

    # apply referral if provided
    if ref:
        referrer = await db_fetchrow("SELECT telegram_id FROM users WHERE referral_code=$1;", ref)
        if referrer and int(referrer["telegram_id"]) != telegram_id:
            ref_tid = int(referrer["telegram_id"])
            await db_exec("""
                UPDATE users
                SET referral_count = referral_count + 1,
                    referral_earnings = referral_earnings + $1,
                    balance = balance + $1,
                    total_earned = total_earned + $1
                WHERE telegram_id=$2;
            """, REF_REWARD, ref_tid)

            await db_exec("""
                INSERT INTO transactions(telegram_id, type, amount, status, description)
                VALUES($1,'earn_referral',$2,'completed',$3);
            """, ref_tid, REF_REWARD, f"Referral bonus (+{REF_REWARD} IRAN)")

            await db_exec("""
                UPDATE users SET referred_by_telegram_id=$1 WHERE telegram_id=$2;
            """, ref_tid, telegram_id)

    row = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    return dict(row)

@app.post("/api/v1/user/init")
async def user_init(payload: dict):
    if not pool:
        raise HTTPException(500, "DB not ready (DATABASE_URL missing?)")

    user = payload.get("user")
    if not user or not user.get("id"):
        raise HTTPException(400, "user.id required")

    ref = payload.get("ref")  # optional
    u = await upsert_user(user, ref)

    return {"success": True, "user": {
        "telegram_id": u["telegram_id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "balance": u["balance"],
        "total_earned": u["total_earned"],
        "referral_code": u["referral_code"],
        "referral_count": u["referral_count"],
        "referral_earnings": u["referral_earnings"],
        "ton_wallet": u["ton_wallet"],
        "total_ads_watched": u["total_ads_watched"],
        "ads_watched_today": u["ads_watched_today"],
    }}

@app.get("/api/v1/user/{telegram_id}")
async def user_get(telegram_id: int):
    row = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not row:
        raise HTTPException(404, "User not found")
    u = dict(row)
    return {
        "telegram_id": u["telegram_id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "balance": u["balance"],
        "total_earned": u["total_earned"],
        "referral_code": u["referral_code"],
        "referral_count": u["referral_count"],
        "referral_earnings": u["referral_earnings"],
        "ton_wallet": u["ton_wallet"],
        "total_ads_watched": u["total_ads_watched"],
        "ads_watched_today": u["ads_watched_today"],
    }

@app.get("/api/v1/user/{telegram_id}/transactions")
async def user_txs(telegram_id: int, limit: int = 20):
    rows = await db_fetch("""
        SELECT * FROM transactions
        WHERE telegram_id=$1
        ORDER BY created_at DESC
        LIMIT $2;
    """, telegram_id, limit)
    return {"transactions": [{
        "id": r["id"],
        "type": r["type"],
        "amount": r["amount"],
        "status": r["status"],
        "description": r["description"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "ton_amount": r["ton_amount"],
        "ton_tx_hash": r["tx_hash"],
    } for r in rows]}

@app.get("/api/v1/ads/status/{telegram_id}")
async def ads_status(telegram_id: int):
    u = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    today = now_utc().date()
    last_reset = u["last_ad_reset"]
    ads_today = int(u["ads_watched_today"] or 0)

    if last_reset is None or last_reset != today:
        ads_today = 0

    can_watch = True
    remaining = 0

    last_watch = u["last_ad_watch"]
    if last_watch:
        elapsed = (now_utc() - last_watch).total_seconds()
        if elapsed < AD_COOLDOWN:
            can_watch = False
            remaining = int(AD_COOLDOWN - elapsed)

    if ads_today >= MAX_ADS_PER_DAY:
        can_watch = False

    return {
        "can_watch": can_watch,
        "remaining_seconds": remaining,
        "ads_watched_today": ads_today,
        "max_ads_per_day": MAX_ADS_PER_DAY,
        "reward_per_ad": AD_REWARD,
        "total_ads_watched": int(u["total_ads_watched"] or 0),
    }

@app.post("/api/v1/ads/watch")
async def ads_watch(payload: dict):
    telegram_id = int(payload.get("telegram_id") or 0)
    if not telegram_id:
        raise HTTPException(400, "telegram_id required")

    u = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    today = now_utc().date()
    last_reset = u["last_ad_reset"]
    ads_today = int(u["ads_watched_today"] or 0)

    if last_reset is None or last_reset != today:
        ads_today = 0
        await db_exec("UPDATE users SET ads_watched_today=0, last_ad_reset=$1 WHERE telegram_id=$2;", today, telegram_id)

    if ads_today >= MAX_ADS_PER_DAY:
        return {"success": False, "message": f"Daily limit {MAX_ADS_PER_DAY} reached"}

    last_watch = u["last_ad_watch"]
    if last_watch:
        elapsed = (now_utc() - last_watch).total_seconds()
        if elapsed < AD_COOLDOWN:
            return {"success": False, "message": "Cooldown", "remaining_seconds": int(AD_COOLDOWN - elapsed)}

    reward = AD_REWARD
    await db_exec("""
        UPDATE users
        SET balance = balance + $1,
            total_earned = total_earned + $1,
            last_ad_watch = now(),
            ads_watched_today = ads_watched_today + 1,
            total_ads_watched = total_ads_watched + 1,
            updated_at = now()
        WHERE telegram_id=$2;
    """, reward, telegram_id)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description)
        VALUES($1,'earn_ad',$2,'completed',$3);
    """, telegram_id, reward, f"Watch Ad (+{reward} IRAN)")

    u2 = await db_fetchrow("SELECT balance, ads_watched_today FROM users WHERE telegram_id=$1;", telegram_id)
    return {"success": True, "reward": reward, "new_balance": u2["balance"], "ads_watched_today": u2["ads_watched_today"]}

@app.get("/api/v1/tasks/{telegram_id}")
async def tasks_for_user(telegram_id: int):
    tasks = await db_fetch("SELECT * FROM tasks WHERE active=true ORDER BY id ASC;")
    completed = await db_fetch("SELECT task_id FROM user_tasks WHERE telegram_id=$1;", telegram_id)
    done = {int(r["task_id"]) for r in completed}
    return {"tasks": [{
        "id": t["id"],
        "title": t["title"],
        "reward": t["reward"],
        "task_type": t["task_type"],
        "task_url": t["url"],
        "completed": int(t["id"]) in done
    } for t in tasks]}

@app.post("/api/v1/tasks/complete")
async def tasks_complete(payload: dict):
    telegram_id = int(payload.get("telegram_id") or 0)
    task_id = int(payload.get("task_id") or 0)
    if not telegram_id or not task_id:
        raise HTTPException(400, "telegram_id and task_id required")

    u = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    t = await db_fetchrow("SELECT * FROM tasks WHERE id=$1 AND active=true;", task_id)
    if not t:
        raise HTTPException(404, "Task not found")

    exists = await db_fetchrow("SELECT 1 FROM user_tasks WHERE telegram_id=$1 AND task_id=$2;", telegram_id, task_id)
    if exists:
        return {"success": False, "message": "Already completed"}

    reward = float(t["reward"])
    await db_exec("INSERT INTO user_tasks(telegram_id, task_id) VALUES($1,$2);", telegram_id, task_id)

    await db_exec("""
        UPDATE users
        SET balance = balance + $1,
            total_earned = total_earned + $1,
            updated_at = now()
        WHERE telegram_id=$2;
    """, reward, telegram_id)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description)
        VALUES($1,'earn_task',$2,'completed',$3);
    """, telegram_id, reward, f"Task: {t['title']} (+{reward} IRAN)")

    u2 = await db_fetchrow("SELECT balance FROM users WHERE telegram_id=$1;", telegram_id)
    return {"success": True, "reward": reward, "new_balance": u2["balance"]}

@app.post("/api/v1/withdraw/request")
async def withdraw_request(payload: dict):
    telegram_id = int(payload.get("telegram_id") or 0)
    amount = float(payload.get("amount") or 0)
    ton_address = (payload.get("ton_address") or "").strip()

    if not telegram_id or not ton_address or amount <= 0:
        raise HTTPException(400, "telegram_id, amount, ton_address required")

    u = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    if amount < MIN_WITHDRAW:
        return {"success": False, "message": f"Minimum withdrawal is {MIN_WITHDRAW} IRAN"}

    if float(u["balance"]) < amount:
        return {"success": False, "message": "Insufficient balance"}

    fee = amount * WITHDRAW_FEE
    net = amount - fee
    ton_amount = net * IRAN_TO_TON_RATE

    # deduct balance
    await db_exec("UPDATE users SET balance = balance - $1, ton_wallet=$2, updated_at=now() WHERE telegram_id=$3;",
                  amount, ton_address, telegram_id)

    await db_exec("""
        INSERT INTO withdraw_requests(telegram_id, iran_amount, ton_amount, ton_address, fee, status)
        VALUES($1,$2,$3,$4,$5,'pending');
    """, telegram_id, amount, ton_amount, ton_address, fee)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description, ton_amount, ton_address, fee)
        VALUES($1,'withdraw',$2,'pending',$3,$4,$5,$6);
    """, telegram_id, -amount, f"Withdraw request ({amount} IRAN)", ton_amount, ton_address, fee)

    u2 = await db_fetchrow("SELECT balance FROM users WHERE telegram_id=$1;", telegram_id)
    return {
        "success": True,
        "message": "Withdraw request submitted (pending)",
        "ton_amount": ton_amount,
        "new_balance": u2["balance"]
    }