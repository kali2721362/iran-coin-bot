import os
import sys
import json
import hashlib
import logging
from datetime import datetime
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

# --- HARDCODED FALLBACKS ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8639953959:AAHX6zYJgqQLo9JExYZ3GuqcEz-yrgjRmVs").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
ADMIN_WALLET = os.getenv("ADMIN_WALLET", "UQCcUO7XRuLyf46obnkSUrec5L00yng7sw8Jut04rlLKCSjB").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://kali2721362.github.io/iran-coin-bot/?v=110000").strip()
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
    telegram_id  = Column(BigInteger, primary_key=True)
    username     = Column(String, nullable=True)
    balance      = Column(BigInteger, default=0)
    vip_tier     = Column(String, default="Free")
    tap_value    = Column(Integer, default=1)
    max_energy   = Column(Integer, default=1000)
    referrer_id  = Column(BigInteger, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

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

if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Base metadata error: {e}")

# --- FASTAPI APP ---
app = FastAPI(title="IRAN Coin Engine v13.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- TELEGRAM SENDER ---
async def send_telegram_now(
    chat_id: int,
    text: str,
    reply_markup: Optional[dict] = None
):
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

# --- HELPER: Get or Create User ---
def get_or_create_user(db, telegram_id: int, username: str = None):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            balance=0,
            vip_tier="Free"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# ═══════════════════════════════════════
# WEBHOOK
# ═══════════════════════════════════════
@app.post("/webhook")
@app.post("/api/v1/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()

        # --- CALLBACK QUERY (Inline Button Press) ---
        if "callback_query" in data:
            cq      = data["callback_query"]
            cq_id   = cq["id"]
            cq_data = cq.get("data", "")
            admin_chat = cq["message"]["chat"]["id"]

            if cq_data.startswith("approve_") or cq_data.startswith("reject_"):
                parts      = cq_data.split("_")
                action     = parts[0]
                w_id       = int(parts[1])
                w_user_id  = int(parts[2])

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
                                    f"✅ Withdrawal #{w_id} APPROVED for user {w_user_id}"
                                )
                            else:
                                w.status = "Rejected"
                                # Refund balance
                                user = db.query(User).filter(
                                    User.telegram_id == w_user_id
                                ).first()
                                if user:
                                    user.balance += w.amount
                                db.commit()
                                await send_telegram_now(
                                    w_user_id,
                                    f"❌ <b>Withdrawal Rejected!</b>\n\n"
                                    f"🪙 {w.amount:,} Coins refunded to your balance.\n"
                                    f"Please contact support for more info."
                                )
                                await send_telegram_now(
                                    admin_chat,
                                    f"❌ Withdrawal #{w_id} REJECTED - coins refunded"
                                )
                    except Exception as e:
                        logger.error(f"Callback Error: {e}")
                    finally:
                        db.close()

            # Answer callback query
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

            # /start
            if txt.startswith("/start"):
                parts    = txt.split()
                ref_id   = None
                if len(parts) > 1 and parts[1].startswith("ref_"):
                    try:
                        ref_id = int(parts[1].replace("ref_", ""))
                    except:
                        ref_id = None

                # DB: create user + referral
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

                        # Reward referrer
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
                                    f"Your friend <b>{username}</b> joined IRAN Coin!\n"
                                    f"🪙 +50 IRAN Coins added to your balance!"
                                )
                        db.close()
                    except Exception as dbe:
                        logger.error(f"DB Error: {dbe}")

                # Welcome message
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

            # /admin
            elif txt == "/admin" and chat_id == ADMIN_ID:
                stats_text = "📊 <b>ADMIN PANEL</b>\n\n"
                if SessionLocal:
                    try:
                        db = SessionLocal()
                        total_users    = db.query(User).count()
                        total_balance  = db.query(User).with_entities(
                            User.balance
                        ).all()
                        total_coins    = sum(u[0] for u in total_balance)
                        pending_w      = db.query(WithdrawalRequest).filter(
                            WithdrawalRequest.status == "Pending"
                        ).count()
                        stats_text += (
                            f"👥 Total Users: <b>{total_users:,}</b>\n"
                            f"🪙 Total Coins: <b>{total_coins:,}</b>\n"
                            f"💼 Pending Withdrawals: <b>{pending_w}</b>\n"
                            f"🤖 Bot: @IranCoinEarnBot\n"
                            f"⚡ Status: Online"
                        )
                        db.close()
                    except Exception as e:
                        stats_text += f"DB Error: {e}"
                await send_telegram_now(ADMIN_ID, stats_text)

            # /broadcast
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
                                            "text": f"📢 <b>IRAN Coin Announcement</b>\n\n{msg_text}",
                                            "parse_mode": "HTML"
                                        },
                                        timeout=5.0
                                    )
                                    sent += 1
                                except:
                                    pass
                        db.close()
                        await send_telegram_now(
                            ADMIN_ID,
                            f"✅ Broadcast sent to {sent} users!"
                        )
                    except Exception as e:
                        await send_telegram_now(ADMIN_ID, f"❌ Broadcast Error: {e}")

            # /addtask
            elif txt.startswith("/addtask") and chat_id == ADMIN_ID:
                # Format: /addtask @channel 50 Title https://link
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
                                f"✅ <b>Sponsor Task Added!</b>\n\n"
                                f"📣 Channel: {channel}\n"
                                f"🏷 Title: {title}\n"
                                f"🪙 Reward: {reward} coins\n"
                                f"🔗 Link: {link}"
                            )
                        except Exception as e:
                            await send_telegram_now(ADMIN_ID, f"❌ Error: {e}")
                else:
                    await send_telegram_now(
                        ADMIN_ID,
                        "⚠️ Format: /addtask @channel 50 Title https://link"
                    )

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
        "status": "IRAN Coin Server v13.0 Running",
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
            "tasks": []
        }
    try:
        db   = SessionLocal()
        user = get_or_create_user(db, user_id)

        # Get sponsor tasks
        tasks = db.query(SponsorTask).filter(
            SponsorTask.active == True
        ).all()
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
            "telegram_id": user.telegram_id,
            "username":    user.username,
            "balance":     user.balance,
            "vip_tier":    user.vip_tier,
            "tap_value":   user.tap_value,
            "max_energy":  user.max_energy,
            "tasks":       tasks_list
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
            "tasks": []
        }

# --- TAP ---
class TapModel(BaseModel):
    user_id: int
    count:   int

@app.post("/api/v1/tap")
async def tap_coins_api(req: TapModel):
    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == req.user_id
            ).first()
            if user:
                user.balance += req.count
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Tap Error: {e}")
    return {"status": "ok"}

# --- WITHDRAW ---
class WithdrawModel(BaseModel):
    telegram_id:    int
    wallet_address: str
    amount:         int

@app.post("/api/v1/withdraw")
async def withdraw_api(req: WithdrawModel):
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

                # Notify admin with approve/reject buttons
                await send_telegram_now(
                    ADMIN_ID,
                    f"💼 <b>WITHDRAWAL REQUEST #{w.id}</b>\n\n"
                    f"👤 User: <code>{req.telegram_id}</code>\n"
                    f"🪙 Amount: <b>{req.amount:,}</b> Coins\n"
                    f"💳 Wallet: <code>{req.wallet_address}</code>\n"
                    f"📅 Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
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

# --- ADS WATCH ---
@app.get("/api/v1/ads/watch")
async def ad_watch_api(telegram_id: int):
    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == telegram_id
            ).first()
            if user:
                user.balance += 100
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Ad Watch Error: {e}")
    return {"status": "rewarded"}

# --- MONETAG ADS ---
@app.get("/api/v1/ads/monetag")
async def monetag_ad_api(
    telegram_id: int,
    source: str = "unknown",
    reward: int = 50
):
    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == telegram_id
            ).first()
            if user:
                user.balance += reward
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Monetag Ad Error: {e}")
    return {"status": "rewarded", "coins": reward}

# --- CPX POSTBACK ---
@app.get("/api/v1/cpx/postback")
async def cpx_postback(
    status:      int   = Query(0),
    trans_id:    str   = Query(""),
    ext_user_id: str   = Query(""),
    amount_local: float = Query(0.0),
    amount_usd:  float = Query(0.0),
    app_id:      str   = Query(""),
    hash:        str   = Query("")
):
    logger.info(
        f"CPX Postback: user={ext_user_id} "
        f"status={status} amount=${amount_usd} "
        f"trans={trans_id}"
    )

    try:
        user_id = int(ext_user_id)
    except:
        return {"status": "error", "message": "invalid user_id"}

    # Coins: 1 USD = 1000 coins
    coins = max(1, int(float(amount_usd) * 1000))

    if not SessionLocal:
        return {"status": "error", "message": "no db"}

    try:
        db   = SessionLocal()
        user = db.query(User).filter(
            User.telegram_id == user_id
        ).first()

        if not user:
            db.close()
            return {"status": "error", "message": "user not found"}

        if status == 1:
            # Check duplicate transaction
            existing = db.query(CPXTransaction).filter(
                CPXTransaction.trans_id == trans_id,
                CPXTransaction.status == 1
            ).first()

            if existing:
                db.close()
                return {"status": "duplicate", "message": "already rewarded"}

            # Add coins
            user.balance += coins

            # Save transaction
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

            # Notify user
            await send_telegram_now(
                user_id,
                f"🎉 <b>Survey Completed!</b>\n\n"
                f"💰 Earned: <b>${amount_usd:.2f}</b>\n"
                f"🪙 <b>+{coins:,} IRAN Coins</b> added!\n"
                f"📊 Transaction ID: <code>{trans_id}</code>"
            )

            logger.info(f"CPX Rewarded: {user_id} +{coins} coins")
            return {"status": "success", "coins_added": coins}

        elif status == 2:
            # Fraud - remove coins
            existing = db.query(CPXTransaction).filter(
                CPXTransaction.trans_id == trans_id
            ).first()

            if existing:
                user.balance = max(0, user.balance - existing.coins)
                existing.status = 2
                db.commit()
                coins_removed = existing.coins
            else:
                user.balance = max(0, user.balance - coins)
                db.commit()
                coins_removed = coins

            db.close()

            # Notify user
            await send_telegram_now(
                user_id,
                f"⚠️ <b>Survey Reversed!</b>\n\n"
                f"🚫 Transaction <code>{trans_id}</code> "
                f"was flagged as fraud.\n"
                f"🪙 <b>-{coins_removed:,} IRAN Coins</b> removed."
            )

            return {"status": "reversed", "coins_removed": coins_removed}

        else:
            db.close()
            return {"status": "ignored", "reason": "incomplete"}

    except Exception as e:
        logger.error(f"CPX Postback Error: {e}")
        return {"status": "error", "message": str(e)}

# --- CHECK MEMBER ---
class CheckMemberModel(BaseModel):
    user_id: int
    channel: str
    reward:  int
    task_id: str

@app.post("/api/v1/check_member")
async def check_member_api(req: CheckMemberModel):
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
                params={
                    "chat_id": req.channel,
                    "user_id": req.user_id
                },
                timeout=8.0
            )
            data   = r.json()
            status = data.get("result", {}).get("status", "")

            if status in ["member", "administrator", "creator"]:
                # Add reward
                if SessionLocal:
                    try:
                        db   = SessionLocal()
                        user = db.query(User).filter(
                            User.telegram_id == req.user_id
                        ).first()
                        if user:
                            user.balance += req.reward
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
    if SessionLocal:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == req.user_id
            ).first()
            if user:
                user.balance += req.reward
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
    if SessionLocal and req.prize > 0:
        try:
            db   = SessionLocal()
            user = db.query(User).filter(
                User.telegram_id == req.user_id
            ).first()
            if user:
                user.balance += req.prize
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Spin Error: {e}")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
