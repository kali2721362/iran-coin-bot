import os
import random
import string
import ssl
from datetime import datetime, timezone

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Header
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


# =========================
# CONFIG
# =========================
AD_REWARD = env_float("AD_REWARD", 10)
AD_COOLDOWN = env_int("AD_COOLDOWN", 3600)
MAX_ADS_PER_DAY = env_int("MAX_ADS_PER_DAY", 10)

MIN_WITHDRAW = env_float("MIN_WITHDRAW", 500)
WITHDRAW_FEE = env_float("WITHDRAW_FEE", 0.05)
IRAN_TO_TON_RATE = env_float("IRAN_TO_TON_RATE", 0.000002)

REF_REWARD = env_float("REF_REWARD", 50)

# =========================
# MINER
# =========================
MINER_RATE_PER_HOUR = env_float("MINER_RATE_PER_HOUR", 30)
MINER_MAX_ACCUM_HOURS = env_float("MINER_MAX_ACCUM_HOURS", 8)

# Optional: different reward by ad_id (UI-like)
AD_REWARD_MAP = {
    1: 15.0,
    2: 20.0,
    3: 25.0,
    4: 20.0,
    5: 15.0,
}

# =========================
# OFFERWALL (CPA)
# =========================
# Example template:
# OFFERWALL_URL_TEMPLATE="https://provider.com/wall?sub_id={telegram_id}"
OFFERWALL_URL_TEMPLATE = os.getenv("OFFERWALL_URL_TEMPLATE", "").strip()

# Must be secret. Offerwall postback should send it as:
#   - query param: secret=...
# or - header: X-Postback-Secret: ...
OFFERWALL_POSTBACK_SECRET = os.getenv("OFFERWALL_POSTBACK_SECRET", "").strip()

# Convert payout unit to IRAN points (internal points)
# If provider sends payout in USD, set something like 1000..5000 depending on your economy.
OFFERWALL_PAYOUT_TO_IRAN = env_float("OFFERWALL_PAYOUT_TO_IRAN", 2000)

# =========================
# TREASURY (TON safety)
# =========================
# withdraw mode:
#   - "off": withdraw disabled
#   - "treasury": allow withdraw only if ton_available >= ton_amount (reserve ton)
WITHDRAW_MODE = os.getenv("WITHDRAW_MODE", "treasury").strip().lower()

# Admin key for manual treasury/withdraw management (do NOT expose)
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()


def get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    # Remove param that can break some parsers
    db_url = db_url.replace("&channel_binding=require", "")
    return db_url


app = FastAPI(title="IRAN Coin API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

pool: asyncpg.Pool | None = None


async def db_exec(sql: str, *args):
    if pool is None:
        raise HTTPException(status_code=503, detail="DB not ready")
    async with pool.acquire() as conn:
        return await conn.execute(sql, *args)


async def db_fetchrow(sql: str, *args):
    if pool is None:
        raise HTTPException(status_code=503, detail="DB not ready")
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args)


async def db_fetch(sql: str, *args):
    if pool is None:
        raise HTTPException(status_code=503, detail="DB not ready")
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


def gen_ref_code(n=8):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


def require_admin(x_admin_key: str | None):
    if not ADMIN_KEY:
        raise HTTPException(503, "ADMIN_KEY not configured")
    if not x_admin_key or x_admin_key != ADMIN_KEY:
        raise HTTPException(401, "Unauthorized")


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

    # Miner
    await db_exec("""
    CREATE TABLE IF NOT EXISTS miner_state (
        telegram_id BIGINT PRIMARY KEY,
        is_active BOOLEAN NOT NULL DEFAULT FALSE,
        started_at TIMESTAMPTZ,
        last_claim_at TIMESTAMPTZ,
        total_mined DOUBLE PRECISION NOT NULL DEFAULT 0
    );
    """)

    # Offerwall events (idempotency)
    await db_exec("""
    CREATE TABLE IF NOT EXISTS offerwall_events (
        event_id TEXT PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        payout DOUBLE PRECISION NOT NULL DEFAULT 0,
        reward_iran DOUBLE PRECISION NOT NULL DEFAULT 0,
        currency TEXT,
        raw TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # Treasury (TON balance & reservation)
    await db_exec("""
    CREATE TABLE IF NOT EXISTS treasury_state (
        id INT PRIMARY KEY,
        ton_balance DOUBLE PRECISION NOT NULL DEFAULT 0,
        ton_reserved DOUBLE PRECISION NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    # ensure single row
    await db_exec("""
    INSERT INTO treasury_state(id, ton_balance, ton_reserved)
    VALUES(1, 0, 0)
    ON CONFLICT (id) DO NOTHING;
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

    db_url = get_database_url()
    if not db_url:
        print("❌ DATABASE_URL is not set")
        return

    ssl_ctx = None
    if os.getenv("DB_SSL", "").lower() in ("1", "true", "yes"):
        ssl_ctx = ssl.create_default_context()

    try:
        pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5, ssl=ssl_ctx)
    except Exception as e:
        pool = None
        print(f"❌ DB connect failed: {e}")
        return

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

    ref_code = gen_ref_code()
    for _ in range(30):
        exists = await db_fetchrow("SELECT 1 FROM users WHERE referral_code=$1;", ref_code)
        if not exists:
            break
        ref_code = gen_ref_code()

    await db_exec("""
        INSERT INTO users(telegram_id, username, first_name, last_name, referral_code)
        VALUES($1,$2,$3,$4,$5);
    """, telegram_id, username, first_name, last_name, ref_code)

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

            await db_exec("UPDATE users SET referred_by_telegram_id=$1 WHERE telegram_id=$2;", ref_tid, telegram_id)

    row = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    return dict(row)


@app.post("/api/v1/user/init")
async def user_init(payload: dict):
    u = payload.get("user")
    if not u or not u.get("id"):
        raise HTTPException(400, "user.id required")

    ref = payload.get("ref")
    user_row = await upsert_user(u, ref)

    return {
        "success": True,
        "user": {
            "telegram_id": user_row["telegram_id"],
            "username": user_row["username"],
            "first_name": user_row["first_name"],
            "last_name": user_row["last_name"],
            "balance": user_row["balance"],
            "total_earned": user_row["total_earned"],
            "referral_code": user_row["referral_code"],
            "referral_count": user_row["referral_count"],
            "referral_earnings": user_row["referral_earnings"],
            "ton_wallet": user_row["ton_wallet"],
            "total_ads_watched": user_row["total_ads_watched"],
            "ads_watched_today": user_row["ads_watched_today"],
        }
    }


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

    return {
        "transactions": [
            {
                "id": r["id"],
                "type": r["type"],
                "amount": r["amount"],
                "status": r["status"],
                "description": r["description"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "ton_amount": r["ton_amount"],
                "ton_tx_hash": r["tx_hash"],
            } for r in rows
        ]
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
        await db_exec("UPDATE users SET ads_watched_today=0, last_ad_reset=$1 WHERE telegram_id=$2;", today, telegram_id)
        ads_today = 0

    if ads_today >= MAX_ADS_PER_DAY:
        return {"success": False, "message": f"Daily limit {MAX_ADS_PER_DAY} reached"}

    last_watch = u["last_ad_watch"]
    if last_watch:
        elapsed = (now_utc() - last_watch).total_seconds()
        if elapsed < AD_COOLDOWN:
            return {"success": False, "message": "Cooldown", "remaining_seconds": int(AD_COOLDOWN - elapsed)}

    ad_id = payload.get("ad_id")
    reward = AD_REWARD_MAP.get(int(ad_id), AD_REWARD) if ad_id else AD_REWARD

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

    return {
        "tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "reward": t["reward"],
                "task_type": t["task_type"],
                "task_url": t["url"],
                "completed": int(t["id"]) in done,
            } for t in tasks
        ]
    }


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


# =========================
# OFFERWALL
# =========================
@app.get("/api/v1/offerwall/link/{telegram_id}")
async def offerwall_link(telegram_id: int):
    # Ensure user exists
    u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    if not OFFERWALL_URL_TEMPLATE:
        return {"success": False, "message": "Offerwall not configured"}

    url = OFFERWALL_URL_TEMPLATE.replace("{telegram_id}", str(telegram_id)).replace("{sub_id}", str(telegram_id))
    return {"success": True, "url": url}


@app.api_route("/api/v1/offerwall/postback", methods=["GET", "POST"])
async def offerwall_postback(
    request: Request,
    x_postback_secret: str | None = Header(default=None),
):
    # Accept params from query OR json body
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        try:
            params = await request.json()
        except:
            params = dict(request.query_params)

    # Secret check
    secret = (params.get("secret") or x_postback_secret or "").strip()
    if OFFERWALL_POSTBACK_SECRET and secret != OFFERWALL_POSTBACK_SECRET:
        raise HTTPException(401, "Invalid secret")

    event_id = str(params.get("event_id") or params.get("click_id") or params.get("conversion_id") or "")
    if not event_id:
        raise HTTPException(400, "event_id required")

    telegram_id = int(params.get("telegram_id") or params.get("sub_id") or params.get("sub") or 0)
    if not telegram_id:
        raise HTTPException(400, "telegram_id/sub_id required")

    payout = float(params.get("payout") or params.get("amount") or 0)
    currency = str(params.get("currency") or "USD")

    # idempotency: ignore if already processed
    exists = await db_fetchrow("SELECT event_id FROM offerwall_events WHERE event_id=$1;", event_id)
    if exists:
        return {"success": True, "message": "Already processed"}

    # user must exist
    u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    reward_iran = max(0.0, payout * OFFERWALL_PAYOUT_TO_IRAN)

    # store event
    await db_exec("""
        INSERT INTO offerwall_events(event_id, telegram_id, payout, reward_iran, currency, raw)
        VALUES($1,$2,$3,$4,$5,$6);
    """, event_id, telegram_id, payout, reward_iran, currency, str(params)[:5000])

    # reward user
    await db_exec("""
        UPDATE users
        SET balance = balance + $1,
            total_earned = total_earned + $1,
            updated_at = now()
        WHERE telegram_id=$2;
    """, reward_iran, telegram_id)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description)
        VALUES($1,'offerwall',$2,'completed',$3);
    """, telegram_id, reward_iran, f"Offerwall reward (+{reward_iran:.2f} IRAN)")

    return {"success": True, "telegram_id": telegram_id, "reward_iran": reward_iran}


# =========================
# TREASURY ADMIN
# =========================
@app.get("/api/v1/admin/treasury")
async def admin_treasury(x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    t = await db_fetchrow("SELECT * FROM treasury_state WHERE id=1;")
    return {"success": True, "ton_balance": float(t["ton_balance"]), "ton_reserved": float(t["ton_reserved"])}


@app.post("/api/v1/admin/treasury/set")
async def admin_treasury_set(payload: dict, x_admin_key: str | None = Header(default=None)):
    require_admin(x_admin_key)
    ton_balance = float(payload.get("ton_balance") or 0)
    ton_reserved = float(payload.get("ton_reserved") or 0)
    if ton_balance < 0 or ton_reserved < 0:
        raise HTTPException(400, "Invalid values")

    await db_exec("""
        UPDATE treasury_state
        SET ton_balance=$1, ton_reserved=$2, updated_at=now()
        WHERE id=1;
    """, ton_balance, ton_reserved)

    return {"success": True}


# =========================
# WITHDRAW (safe)
# =========================
@app.post("/api/v1/withdraw/request")
async def withdraw_request(payload: dict):
    if WITHDRAW_MODE == "off":
        return {"success": False, "message": "Withdraw is disabled"}

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

    if WITHDRAW_MODE == "treasury":
        t = await db_fetchrow("SELECT * FROM treasury_state WHERE id=1;")
        ton_balance = float(t["ton_balance"])
        ton_reserved = float(t["ton_reserved"])
        if (ton_balance - ton_reserved) < ton_amount:
            return {"success": False, "message": "Treasury not funded yet. Try later."}

        # reserve TON to avoid over-commitment
        await db_exec("""
            UPDATE treasury_state
            SET ton_reserved = ton_reserved + $1, updated_at=now()
            WHERE id=1;
        """, ton_amount)

    # deduct user balance
    await db_exec("""
        UPDATE users
        SET balance = balance - $1,
            ton_wallet=$2,
            updated_at=now()
        WHERE telegram_id=$3;
    """, amount, ton_address, telegram_id)

    await db_exec("""
        INSERT INTO withdraw_requests(telegram_id, iran_amount, ton_amount, ton_address, fee, status)
        VALUES($1,$2,$3,$4,$5,'pending');
    """, telegram_id, amount, ton_amount, ton_address, fee)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description, ton_amount, ton_address, fee)
        VALUES($1,'withdraw',$2,'pending',$3,$4,$5,$6);
    """, telegram_id, -amount, f"Withdraw request ({amount} IRAN)", ton_amount, ton_address, fee)

    u2 = await db_fetchrow("SELECT balance FROM users WHERE telegram_id=$1;", telegram_id)
    return {"success": True, "message": "Withdraw request submitted (pending)", "ton_amount": ton_amount, "new_balance": u2["balance"]}


# =========================
# MINER ENDPOINTS
# =========================
def _pending_miner(now, last_ts):
    if not last_ts:
        return 0.0
    elapsed = (now - last_ts).total_seconds()
    hours = max(0.0, elapsed / 3600.0)
    hours = min(hours, MINER_MAX_ACCUM_HOURS)
    return hours * MINER_RATE_PER_HOUR


@app.get("/api/v1/miner/status/{telegram_id}")
async def miner_status(telegram_id: int):
    m = await db_fetchrow("SELECT * FROM miner_state WHERE telegram_id=$1;", telegram_id)
    now = now_utc()

    if not m:
        return {"success": True, "active": False, "pending": 0.0, "rate_per_hour": MINER_RATE_PER_HOUR}

    last_ts = m["last_claim_at"] or m["started_at"]
    pending = _pending_miner(now, last_ts) if m["is_active"] else 0.0

    return {"success": True, "active": bool(m["is_active"]), "pending": pending, "rate_per_hour": MINER_RATE_PER_HOUR}


@app.post("/api/v1/miner/start")
async def miner_start(payload: dict):
    telegram_id = int(payload.get("telegram_id") or 0)
    if not telegram_id:
        raise HTTPException(400, "telegram_id required")

    u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    now = now_utc()
    await db_exec("""
        INSERT INTO miner_state(telegram_id, is_active, started_at, last_claim_at)
        VALUES($1, TRUE, $2, $2)
        ON CONFLICT (telegram_id)
        DO UPDATE SET is_active=TRUE,
                      started_at=COALESCE(miner_state.started_at, $2),
                      last_claim_at=$2;
    """, telegram_id, now)

    return {"success": True, "message": "Mining started"}


@app.post("/api/v1/miner/claim")
async def miner_claim(payload: dict):
    telegram_id = int(payload.get("telegram_id") or 0)
    if not telegram_id:
        raise HTTPException(400, "telegram_id required")

    u = await db_fetchrow("SELECT * FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    m = await db_fetchrow("SELECT * FROM miner_state WHERE telegram_id=$1;", telegram_id)
    if not m or not m["is_active"]:
        return {"success": False, "message": "Miner is not active"}

    now = now_utc()
    last_ts = m["last_claim_at"] or m["started_at"]
    pending = _pending_miner(now, last_ts)

    if pending <= 0.0:
        return {"success": False, "message": "Nothing to claim yet"}

    await db_exec("""
        UPDATE users
        SET balance = balance + $1,
            total_earned = total_earned + $1,
            updated_at = now()
        WHERE telegram_id=$2;
    """, pending, telegram_id)

    await db_exec("""
        UPDATE miner_state
        SET last_claim_at=$1,
            total_mined = total_mined + $2
        WHERE telegram_id=$3;
    """, now, pending, telegram_id)

    await db_exec("""
        INSERT INTO transactions(telegram_id, type, amount, status, description)
        VALUES($1,'miner',$2,'completed',$3);
    """, telegram_id, pending, f"Miner claim (+{pending:.2f} IRAN)")

    u2 = await db_fetchrow("SELECT balance FROM users WHERE telegram_id=$1;", telegram_id)
    return {"success": True, "claimed": pending, "new_balance": u2["balance"]}