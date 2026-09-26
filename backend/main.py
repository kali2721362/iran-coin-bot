import os
import sys
import json
import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, BigInteger, String, Integer, Float, DateTime, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRANCoinDirect")

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8639953959:AAHX6zYJgqQLo9JExYZ3GuqcEz-yrgjRmVs").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
ADMIN_WALLET = os.getenv("ADMIN_WALLET", "UQCcUO7XRuLyf46obnkSUrec5L00yng7sw8Jut04rlLKCSjB").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://kali2721362.github.io/iran-coin-bot/?v=150000").strip()
CPX_SECRET = os.getenv("OFFERWALL_POSTBACK_SECRET", "Aa@2721362272136227213622721362").strip()
PORT = int(os.getenv("PORT", 8000))

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- DATABASE ---
Base = declarative_base()
engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        logger.error(f"DB Engine Init Error: {e}")

# --- MODELS ---
class User(Base):
    __tablename__ = "users"
    telegram_id   = Column(BigInteger, primary_key=True)
    username      = Column(String, nullable=True)
    balance       = Column(BigInteger, default=0)
    vip_tier      = Column(String, default="Free")
    tap_value     = Column(Integer, default=1)
    max_energy    = Column(Integer, default=1000)
    referrer_id   = Column(BigInteger, nullable=True)
    last_mine     = Column(DateTime, nullable=True)
    mine_level    = Column(Integer, default=1)
    total_taps    = Column(BigInteger, default=0)
    last_tap_time = Column(Float, default=0)
    tap_count_window = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    hash        = Column(String, primary_key=True)
    telegram_id = Column(BigInteger)
    amount      = Column(Float)
    tier        = Column(String)
    created_at  = Column(DateTime, default=datetime.utcnow)

class WithdrawalRequest(Base):
    __tablename__ = "withdrawals"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id    = Column(BigInteger)
    wallet_address = Column(String)
    amount         = Column(BigInteger)
    status         = Column(String, default="Pending")
    created_at     = Column(DateTime, default=datetime.utcnow)

class CPXTransaction(Base):
    __tablename__ = "cpx_transactions"
    trans_id    = Column(String, primary_key=True)
    telegram_id = Column(BigInteger)
    amount_usd  = Column(Float, default=0.0)
    coins       = Column(Integer, default=0)
    status      = Column(Integer, default=1)
    created_at  = Column(DateTime, default=datetime.utcnow)

class SponsorTask(Base):
    __tablename__ = "sponsor_tasks"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    channel    = Column(String)
    reward     = Column(Integer, default=50)
    title      = Column(String)
    link       = Column(String)
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TapLog(Base):
    __tablename__ = "tap_logs"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger)
    count       = Column(Integer)
    ip          = Column(String, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

class AdLog(Base):
    __tablename__ = "ad_logs"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger)
    ad_type     = Column(String)
    reward      = Column(Integer)
    created_at  = Column(DateTime, default=datetime.utcnow)

if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Base metadata error: {e}")

# --- FASTAPI ---
app = FastAPI(title="IRAN Coin Engine v15.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ANTI-CHEAT CONFIG ---
MAX_TAPS_PER_SECOND = 10
MAX_TAPS_PER_REQUEST = 500
MAX_AD_PER_HOUR = 3
MINE_INTERVAL_HOURS = 8

# VIP configs
VIP_CONFIG = {
    "Free":    {"tap": 1,  "energy": 1000,  "daily": 0,    "mine_rate": 10},
    "Bronze":  {"tap": 2,  "energy": 1500,  "daily": 500,  "mine_rate": 25},
    "Silver":  {"tap": 5,  "energy": 3000,  "daily": 2000, "mine_rate": 60},
    "Gold":    {"tap": 10, "energy": 5000,  "daily": 5000, "mine_rate": 150},
    "Diamond": {"tap": 25, "energy": 10000, "daily": 15000,"mine_rate": 400},
}

# --- TELEGRAM SENDER ---
async def send_telegram_now(chat_id: int, text: str, reply_markup: Optional[dict] = None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload, timeout=12.0)
            logger.info(f"Telegram Send: {r.status_code}")
        except Exception as e:
            logger.error(f"Telegram Send Error: {e}")

# --- HELPERS ---
def get_or_create_user(db, telegram_id: int, username: str = None):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            balance=0,
            vip_tier="Free",
            tap_value=1,
            max_energy=1000
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def anti_cheat_tap(user: User, count: int) -> tuple[bool, str, int]:
    """
    Returns: (is_valid, reason, safe_count)
    """
    now = time.time()

    # 1. Max taps per request
    if count > MAX_TAPS_PER_REQUEST:
        return False, "Too many taps in one request", MAX_TAPS_PER_REQUEST

    # 2. Rate limiting - reset window every second
    if now - user.last_tap_time > 1.0:
        user.tap_count_window = 0
        user.last_tap_time = now

    user.tap_count_window += count

    # 3. Max taps per second
    if user.tap_count_window > MAX_TAPS_PER_SECOND * 2:
        return False, "Tap rate too high", 0

    # 4. Reasonable count check
    safe_count = min(count, MAX_TAPS_PER_REQUEST)

    return True, "ok", safe_count

def check_mine_ready(user: User) -> tuple[bool, int, int]:
    """
    Returns: (is_ready, coins_to_mine, hours_remaining)
    """
    if not user.last_mine:
        return True, get_mine_amount(user), 0

    now = datetime.utcnow()
    elapsed = now - user.last_mine
    hours_elapsed = elapsed.total_seconds() / 3600

    if hours_elapsed >= MINE_INTERVAL_HOURS:
        # Calculate how many intervals passed (max 3)
        intervals = min(int(hours_elapsed / MINE_INTERVAL_HOURS), 3)
        coins = get_mine_amount(user) * intervals
        return True, coins, 0
    else:
        hours_remaining = MINE_INTERVAL_HOURS - hours_elapsed
        return False, 0, int(hours_remaining)

def get_mine_amount(user: User) -> int:
    """Get mining amount based on VIP tier"""
    config = VIP_CONFIG.get(user.vip_tier, VIP_CONFIG["Free"])
    base = config["mine_rate"]
    # Level multiplier
    level_bonus = (user.mine_level - 1) * 5
    return base + level_bonus

# ═══════════════════════════════════════
# WEBHOOK
# ═══════════════════════════════════════
@app.post("/webhook")
@app.post("/api/v1/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()

        # --- CALLBACK QUERY ---
        if "callback_query" in data:
            cq      = data["callback_query"]
            cq_id   = cq["id"]
            cq_data = cq.get("data", "")
            admin_chat = cq["message"]["chat"]["id"]

            if cq_data.startswith("approve_") or cq_data.startswith("reject_"):
                parts     = cq_data.split("_")
                action    = parts[0]
                w_id      = int(parts[1])
                w_user_id = int(parts[2])

                if SessionLocal:
                    db = SessionLocal()
                    try:
                        w = db.query(WithdrawalRequest).filter(
                            WithdrawalRequest.id == w_id
                        ).first()
                        if w:
                            if action == "approve":
                                w.status = "Approved"
                                db.commit()
                                await send_telegram_now(
                                    w_user_id,
                                    f"✅ <b>Withdrawal Approved!</b>\n\n"
                                    f"🪙 {w.amount:,} IRAN Coins\n"
                                    f"💼 Wallet: <code>{w.wallet_address}</code>\n\n"
                                    f"TON will be sent within 24 hours!"
                                )
                                await send_telegram_now(
                                    admin_chat,
                                    f"✅ Withdrawal #{w_id} APPROVED"
                                )
                            else:
                                w.status = "Rejected"
                                user = db.query(User).filter(
                                    User.telegram_id == w_user_id
                                ).first()
                                if user:
                                    user.balance += w.amount
                                db.commit()
                                await send_telegram_now(
                                    w_user_id,
                                    f"❌ <b>Withdrawal Rejected!</b>\n\n"
                                    f"🪙 {w.amount:,} Coins refunded.\n"
                                    f"Please contact support."
                                )
                                await send_telegram_now(
                                    admin_chat,
                                    f"❌ Withdrawal #{w_id} REJECTED - refunded"
                                )
                    except Exception as e:
                        logger.error(f"Callback Error: {e}")
                    finally:
                        db.close()

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
                    json={"callback_query_id": cq_id}
                )
            return {"status": "ok"}

        # --- MESSAGE ---
        if "message" in data:
            message  = data["message"]
            chat_id  = message["chat"]["id"]
            txt      = message.get("text", "")
            username = message.get("from", {}).get("first_name", "Player")

            if txt.startswith("/start"):
                parts  = txt.split()
                ref_id = None
                if len(parts) > 1 and parts[1].startswith("ref_"):
                    try:
                        ref_id = int(parts[1].replace("ref_", ""))
                    except:
                        ref_id = None

                if SessionLocal:
                    try:
                        db = SessionLocal()
                        user = db.query(User).filter(
                            User.telegram_id == chat_id
                        ).first()
                        is_new = False
                        if not user:
                            is_new = True
                            user = User(
                                telegram_id=chat_id,
                                username=username,
                                balance=0,
                                referrer_id=ref_id
                            )
                            db.add(user)
                            db.commit()

                        if is_new and ref_id and ref_id != chat_id:
                            referrer = db.query(User).filter(
                                User.telegram_id == ref_id
                            ).first()
                            if referrer:
                                referrer.balance += 50
                                db.commit()
                                await send_telegram_now(
                                    ref_id,
                                    f"🎉 <b>Referral Bonus!</b>\n\n"
                                    f"Your friend <b>{username}</b> joined!\n"
                                    f"🪙 +50 IRAN Coins added!"
                                )
                        db.close()
                    except Exception as e:
                        logger.error(f"DB Error: {e}")

                welcome_text = (
                    f"🇮🇷 <b>Welcome to IRAN Coin, {username}!</b>\n\n"
                    f"⛏ Mine tokens, complete tasks,\n"
                    f"🎡 Spin the daily wheel,\n"
                    f"👑 Upgrade your VIP level!\n\n"
                    f"Tap below to start mining now 👇"
                )
                keyboard = {
                    "inline_keyboard": [[
                        {
                            "text": "🚀 Play IRAN Coin Now",
                            "web_app": {"url": MINI_APP_URL}
                        }
                    ], [
                        {
                            "text": "📢 Official Channel",
                            "url": "https://t.me/IRANCoin_Official"
                        },
                        {
                            "text": "💬 Support Group",
                            "url": "https://t.me/IRANCoinGroup"
                        }
                    ]]
                }
                await send_telegram_now(chat_id, welcome_text, keyboard)

            elif txt == "/admin" and chat_id == ADMIN_ID:
                stats_text = "📊 <b>ADMIN PANEL v15.0</b>\n\n"
                if SessionLocal:
                    try:
                        db = SessionLocal()
                        total_users   = db.query(User).count()
                        total_balance = db.query(User).with_entities(User.balance).all()
                        total_coins   = sum(u[0] for u in total_balance)
                        pending_w     = db.query(WithdrawalRequest).filter(
                            WithdrawalRequest.status == "Pending"
                        ).count()
                        stats_text += (
                            f"👥 Total Users: <b>{total_users:,}</b>\n"
                            f"🪙 Total Coins: <b>{total_coins:,}</b>\n"
                            f"💼 Pending Withdrawals: <b>{pending_w}</b>\n"
                            f"⛏ Mine Interval: <b>{MINE_INTERVAL_HOURS}h</b>\n"
                            f"🛡 Anti-Cheat: <b>Active</b>\n"
                            f"⚡ Status: <b>Online</b>"
                        )
                        db.close()
                    except Exception as e:
                        stats_text += f"DB Error: {e}"
                await send_telegram_now(ADMIN_ID, stats_text)

            elif txt.startswith("/broadcast") and chat_id == ADMIN_ID:
                msg_text = txt.replace("/broadcast", "").strip()
                if msg_text and SessionLocal:
                    try:
                        db = SessionLocal()
                        all_users = db.query(User).all()
                        sent = 0
                        async with httpx.AsyncClient() as client:
                            for u in all_users:
                                try:
                                    await client.post(
                                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                        json={
                                            "chat_id": u.telegram_id,
                                            "text": f"📢 <b>IRAN Coin</b>\n\n{msg_text}",
                                            "parse_mode": "HTML"
                                        },
                                        timeout=5.0
                                    )
                                    sent += 1
                                except:
                                    pass
                        db.close()
                        await send_telegram_now(ADMIN_ID, f"✅ Sent to {sent} users!")
                    except Exception as e:
                        await send_telegram_now(ADMIN_ID, f"❌ Error: {e}")

            elif txt.startswith("/addtask") and chat_id == ADMIN_ID:
                parts = txt.split(" ", 4)
                if len(parts) >= 5:
                    channel = parts[1]
                    reward  = int(parts[2])
                    title   = parts[3]
                    link    = parts[4]
                    if SessionLocal:
                        try:
                            db = SessionLocal()
                            task = SponsorTask(
                                channel=channel,
                                reward=reward,
                                title=title,
                                link=link,
                                active=True
                            )
                            db.add(task)
                            db.commit()
                            db.close()
                            await send_telegram_now(
                                ADMIN_ID,
                                f"✅ <b>Task Added!</b>\n\n"
                                f"📣 {channel}\n"
                                f"🏷 {title}\n"
                                f"🪙 {reward} coins\n"
                                f"🔗 {link}"
                            )
                        except Exception as e:
                            await send_telegram_now(ADMIN_ID, f"❌ Error: {e}")

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return {"status": "ok"}

# ═══════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════

@app.get("/")
def read_root():
    return {
        "status": "IRAN Coin v15.0",
        "anti_cheat": "active",
        "app_url": MINI_APP_URL
    }

# --- GET USER ---
@app.get("/api/v1/user/{user_id}")
async def get_user_api(user_id: int):
    if not SessionLocal:
        return {
            "telegram_id": user_id,
            "balance": 0,
            "vip_tier": "Free",
            "tap_value": 1,
            "max_energy": 1000,
            "mine_ready": True,
            "mine_coins": 10,
            "mine_hours_left": 0,
            "tasks": []
        }
    try:
        db   = SessionLocal()
        user = get_or_create_user(db, user_id)

        # Check mine status
        mine_ready, mine_coins, mine_hours = check_mine_ready(user)

        # Get tasks
        tasks = db.query(SponsorTask).filter(SponsorTask.active == True).all()
        tasks_list = [
            {
                "id": t.id,
                "title": t.title,
                "reward": t.reward,
                "link": t.link,
                "channel": t.channel
            }
            for t in tasks
        ]

        res = {
            "telegram_id":    user.telegram_id,
            "username":       user.username,
            "balance":        user.balance,
            "vip_tier":       user.vip_tier,
            "tap_value":      user.tap_value,
            "max_energy":     user.max_energy,
            "mine_level":     user.mine_level,
            "mine_ready":     mine_ready,
            "mine_coins":     mine_coins,
            "mine_hours_left": mine_hours,
            "tasks":          tasks_list
        }
        db.close()
        return res
    except Exception as e:
        logger.error(f"Get User Error: {e}")
        return {
            "telegram_id": user_id,
            "balance": 0,
            "vip_tier": "Free",
            "tap_value": 1,
            "max_energy": 1000,
            "mine_ready": True,
            "mine_coins": 10,
            "mine_hours_left": 0,
            "tasks": []
        }

# --- TAP (با Anti-Cheat) ---
class TapModel(BaseModel):
    user_id: int
    count:   int

@app.post("/api/v1/tap")
async def tap_coins_api(req: TapModel):
    if not SessionLocal:
        return {"status": "ok", "coins_added": req.count}

    try:
        db   = SessionLocal()
        user = db.query(User).filter(User.telegram_id == req.user_id).first()

        if not user:
            db.close()
            return {"status": "error", "message": "user not found"}

        # Anti-cheat check
        is_valid, reason, safe_count = anti_cheat_tap(user, req.count)

        if not is_valid or safe_count == 0:
            logger.warning(f"Anti-cheat blocked tap: {req.user_id} - {reason}")
            db.close()
            return {"status": "blocked", "reason": reason}

        # Add coins
        user.balance    += safe_count
        user.total_taps += safe_count
        user.last_tap_time = time.time()
        db.commit()

        # Log tap
        tap_log = TapLog(
            telegram_id=req.user_id,
            count=safe_count
        )
        db.add(tap_log)
        db.commit()
        db.close()

        return {"status": "ok", "coins_added": safe_count}

    except Exception as e:
        logger.error(f"Tap Error: {e}")
        return {"status": "ok"}

# --- MINE (Auto Mining) ---
class MineModel(BaseModel):
    user_id: int

@app.post("/api/v1/mine")
async def mine_api(req: MineModel):
    if not SessionLocal:
        return {"status": "error", "message": "no db"}

    try:
        db   = SessionLocal()
        user = db.query(User).filter(User.telegram_id == req.user_id).first()

        if not user:
            db.close()
            return {"status": "error", "message": "user not found"}

        mine_ready, coins, hours_left = check_mine_ready(user)

        if not mine_ready:
            db.close()
            return {
                "status": "not_ready",
                "hours_left": hours_left,
                "message": f"Mine ready in {hours_left}h"
            }

        # Add coins
        user.balance  += coins
        user.last_mine = datetime.utcnow()
        db.commit()
        db.close()

        return {
            "status": "success",
            "coins_added": coins,
            "next_mine_hours": MINE_INTERVAL_HOURS
        }

    except Exception as e:
        logger.error(f"Mine Error: {e}")
        return {"status": "error", "message": str(e)}

# --- WITHDRAW ---
class WithdrawModel(BaseModel):
    telegram_id:    int
    wallet_address: str
    amount:         int

@app.post("/api/v1/withdraw")
async def withdraw_api(req: WithdrawModel):
    # Anti-cheat: minimum withdrawal
    if req.amount < 10000:
        return {"status": "error", "message": "Minimum 10,000 coins"}

    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == req.telegram_id
            ).first()

            if user and user.balance >= req.amount:
                user.balance -= req.amount
                w = WithdrawalRequest(
                    telegram_id=req.telegram_id,
                    wallet_address=req.wallet_address,
                    amount=req.amount
                )
                db.add(w)
                db.commit()
                db.refresh(w)

                await send_telegram_now(
                    ADMIN_ID,
                    f"💼 <b>WITHDRAWAL #{w.id}</b>\n\n"
                    f"👤 User: <code>{req.telegram_id}</code>\n"
                    f"🪙 Amount: <b>{req.amount:,}</b> Coins\n"
                    f"💳 Wallet: <code>{req.wallet_address}</code>\n"
                    f"📅 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                    {
                        "inline_keyboard": [[
                            {
                                "text": "✅ Approve & Pay",
                                "callback_data": f"approve_{w.id}_{req.telegram_id}"
                            },
                            {
                                "text": "❌ Reject",
                                "callback_data": f"reject_{w.id}_{req.telegram_id}"
                            }
                        ]]
                    }
                )
            db.close()
        except Exception as e:
            logger.error(f"Withdraw Error: {e}")

    return {"status": "success"}

# --- ADS (با Anti-Cheat) ---
@app.get("/api/v1/ads/watch")
async def ad_watch_api(telegram_id: int):
    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(User.telegram_id == telegram_id).first()

            if user:
                # Anti-cheat: چک تعداد آگهی در ساعت
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_ads = db.query(AdLog).filter(
                    AdLog.telegram_id == telegram_id,
                    AdLog.created_at > one_hour_ago
                ).count()

                if recent_ads >= MAX_AD_PER_HOUR:
                    db.close()
                    return {
                        "status": "limited",
                        "message": f"Max {MAX_AD_PER_HOUR} ads per hour"
                    }

                # Add reward
                reward = 50  # کاهش از 100 به 50
                user.balance += reward

                # Log ad
                ad_log = AdLog(
                    telegram_id=telegram_id,
                    ad_type="video",
                    reward=reward
                )
                db.add(ad_log)
                db.commit()
                db.close()

                return {"status": "rewarded", "coins": reward}

        except Exception as e:
            logger.error(f"Ad Watch Error: {e}")

    return {"status": "rewarded", "coins": 50}

# --- MONETAG ---
@app.get("/api/v1/ads/monetag")
async def monetag_ad_api(
    telegram_id: int,
    source: str = "unknown",
    reward: int = 25  # کاهش از 50 به 25
):
    # Anti-cheat: max reward per call
    safe_reward = min(reward, 25)

    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(User.telegram_id == telegram_id).first()

            if user:
                # چک تعداد آگهی در ساعت
                one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                recent_ads = db.query(AdLog).filter(
                    AdLog.telegram_id == telegram_id,
                    AdLog.created_at > one_hour_ago
                ).count()

                if recent_ads >= MAX_AD_PER_HOUR:
                    db.close()
                    return {"status": "limited", "coins": 0}

                user.balance += safe_reward

                ad_log = AdLog(
                    telegram_id=telegram_id,
                    ad_type=f"monetag_{source}",
                    reward=safe_reward
                )
                db.add(ad_log)
                db.commit()
                db.close()

        except Exception as e:
            logger.error(f"Monetag Error: {e}")

    return {"status": "rewarded", "coins": safe_reward}

# --- CPX POSTBACK ---
@app.get("/api/v1/cpx/postback")
async def cpx_postback(
    status:       int   = Query(0),
    trans_id:     str   = Query(""),
    ext_user_id:  str   = Query(""),
    amount_usd:   float = Query(0.0),
    hash:         str   = Query("")
):
    try:
        user_id = int(ext_user_id)
    except:
        return {"status": "error"}

    # 1 USD = 500 coins (کاهش از 1000)
    coins = max(1, int(float(amount_usd) * 500))

    if not SessionLocal:
        return {"status": "error"}

    try:
        db   = SessionLocal()
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            db.close()
            return {"status": "error"}

        if status == 1:
            existing = db.query(CPXTransaction).filter(
                CPXTransaction.trans_id == trans_id,
                CPXTransaction.status == 1
            ).first()

            if existing:
                db.close()
                return {"status": "duplicate"}

            user.balance += coins
            cpx_tx = CPXTransaction(
                trans_id=trans_id,
                telegram_id=user_id,
                amount_usd=amount_usd,
                coins=coins,
                status=1
            )
            db.add(cpx_tx)
            db.commit()
            db.close()

            await send_telegram_now(
                user_id,
                f"🎉 <b>Survey Completed!</b>\n\n"
                f"💰 Earned: <b>${amount_usd:.2f}</b>\n"
                f"🪙 <b>+{coins:,} IRAN Coins</b> added!\n"
                f"📊 ID: <code>{trans_id}</code>"
            )
            return {"status": "success", "coins_added": coins}

        elif status == 2:
            existing = db.query(CPXTransaction).filter(
                CPXTransaction.trans_id == trans_id
            ).first()
            if existing:
                user.balance = max(0, user.balance - existing.coins)
                existing.status = 2
                db.commit()
            db.close()
            return {"status": "reversed"}

        db.close()
        return {"status": "ignored"}

    except Exception as e:
        logger.error(f"CPX Error: {e}")
        return {"status": "error"}

# --- CHECK MEMBER ---
class CheckMemberModel(BaseModel):
    user_id: int
    channel: str
    reward:  int
    task_id: str

@app.post("/api/v1/check_member")
async def check_member_api(req: CheckMemberModel):
    # Anti-cheat: max reward per task
    safe_reward = min(req.reward, 100)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
                params={"chat_id": req.channel, "user_id": req.user_id},
                timeout=8.0
            )
            data   = r.json()
            status = data.get("result", {}).get("status", "")

            if status in ["member", "administrator", "creator"]:
                if SessionLocal:
                    try:
                        db   = SessionLocal()
                        user = db.query(User).filter(
                            User.telegram_id == req.user_id
                        ).first()
                        if user:
                            user.balance += safe_reward
                            db.commit()
                        db.close()
                    except Exception as e:
                        logger.error(f"Check Member DB Error: {e}")
                return {"success": True}
            else:
                return {"success": False}
    except Exception as e:
        logger.error(f"Check Member Error: {e}")
        return {"success": False}

# --- STREAK ---
class StreakModel(BaseModel):
    user_id: int
    day:     int
    reward:  int

@app.post("/api/v1/streak")
async def streak_api(req: StreakModel):
    # Anti-cheat: max streak reward
    safe_reward = min(req.reward, 100)

    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(User.telegram_id == req.user_id).first()
            if user:
                user.balance += safe_reward
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Streak Error: {e}")

    return {"status": "ok"}

# --- SPIN ---
class SpinModel(BaseModel):
    user_id: int
    prize:   int

@app.post("/api/v1/spin")
async def spin_api(req: SpinModel):
    # Anti-cheat: max spin prize
    safe_prize = min(req.prize, 100)

    if SessionLocal and safe_prize > 0:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(User.telegram_id == req.user_id).first()
            if user:
                user.balance += safe_prize
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Spin Error: {e}")

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
