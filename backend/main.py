import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, BigInteger, String, Integer, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRANCoinBackend")

# --- ENVIRONMENT VARIABLES ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
ADMIN_WALLET = os.getenv("ADMIN_WALLET", "UQCcUO7XRuLyf46obnkSUrec5L00yng7sw8Jut04rlLKCSjB")
TON_API_KEY = os.getenv("TONCENTER_API_KEY", "1d85a1804835e8c0c7458f49f9df7ed0c03d18c067999ec428fc1bd9136a0a8c")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://kali2721362.github.io/iran-coin-bot/?v=110000")
PORT = int(os.getenv("PORT", 8000))

# Fix PostgreSQL schema for SQLAlchemy if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- DATABASE SETUP ---
Base = declarative_base()
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    balance = Column(BigInteger, default=0)
    vip_tier = Column(String, default="Free") # Free, Bronze, Silver, Gold, Diamond
    tap_value = Column(Integer, default=1)
    max_energy = Column(Integer, default=1000)
    referrer_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"
    hash = Column(String, primary_key=True)
    telegram_id = Column(BigInteger)
    amount = Column(Float)
    tier = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class WithdrawalRequest(Base):
    __tablename__ = "withdrawals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger)
    wallet_address = Column(String)
    amount = Column(BigInteger)
    status = Column(String, default="Pending") # Pending, Approved, Rejected
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# VIP Tiers Configuration
VIP_CONFIG = {
    "Bronze": {"price": 0.1, "tap": 2, "energy": 1500},
    "Silver": {"price": 0.5, "tap": 5, "energy": 3000},
    "Gold": {"price": 1.5, "tap": 10, "energy": 5000},
    "Diamond": {"price": 3.0, "tap": 25, "energy": 10000},
}

# --- FASTAPI APP ---
app = FastAPI(title="IRAN Coin Backend Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPER TELEGRAM BOT SENDER ---
async def send_telegram_msg(chat_id: int, text: str, reply_markup: Optional[dict] = None):
    if not BOT_TOKEN:
        return
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
            await client.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

# --- TON BLOCKCHAIN MONITOR (AUTO VIP VERIFICATION) ---
async def ton_blockchain_monitor():
    """Background task checking TON Center API for incoming payments."""
    url = f"https://toncenter.com/api/v2/getTransactions?address={ADMIN_WALLET}&limit=20&api_key={TON_API_KEY}"
    logger.info("TON Blockchain Monitor Background Engine Started.")
    
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        db = SessionLocal()
                        for tx in data.get("result", []):
                            tx_hash = tx.get("transaction_id", {}).get("hash", "")
                            if not tx_hash:
                                continue

                            # Check if already processed
                            if not db.query(Transaction).filter(Transaction.hash == tx_hash).first():
                                msg = tx.get("in_msg", {})
                                comment = msg.get("message", "").strip()
                                value_ton = int(msg.get("value", 0)) / 1e9

                                if comment.startswith("VIP_"):
                                    parts = comment.split("_")
                                    if len(parts) == 3:
                                        tier = parts[1]
                                        user_id = int(parts[2])

                                        if tier in VIP_CONFIG and value_ton >= (VIP_CONFIG[tier]["price"] * 0.9):
                                            # 1. Record Transaction
                                            new_tx = Transaction(hash=tx_hash, telegram_id=user_id, amount=value_ton, tier=tier)
                                            db.add(new_tx)

                                            # 2. Upgrade User VIP Status
                                            u = db.query(User).filter(User.telegram_id == user_id).first()
                                            if u:
                                                u.vip_tier = tier
                                                u.tap_value = VIP_CONFIG[tier]["tap"]
                                                u.max_energy = VIP_CONFIG[tier]["energy"]
                                                db.commit()

                                                # Notify User on Telegram
                                                msg_text = (
                                                    f"🎉 <b>VIP MEMBERSHIP ACTIVATED!</b>\n\n"
                                                    f"👑 Tier: <b>{tier} VIP</b>\n"
                                                    f"⚡ Tap Power: <b>+{VIP_CONFIG[tier]['tap']} Coins/Tap</b>\n"
                                                    f"🔋 Max Energy: <b>{VIP_CONFIG[tier]['energy']}</b>\n\n"
                                                    f"Thank you for supporting IRAN Coin!"
                                                )
                                                asyncio.create_task(send_telegram_msg(user_id, msg_text))

                                                # Notify Admin
                                                admin_alert = (
                                                    f"💰 <b>NEW TON VIP PAYMENT RECEIVED!</b>\n\n"
                                                    f"👤 User: <code>{user_id}</code>\n"
                                                    f"💎 Tier: <b>{tier} VIP</b>\n"
                                                    f"💵 Amount: <b>{value_ton} TON</b>\n"
                                                    f"🔗 Memo: <code>{comment}</code>"
                                                )
                                                asyncio.create_task(send_telegram_msg(ADMIN_ID, admin_alert))

                                            db.commit()
                        db.close()
            await asyncio.sleep(45)
        except Exception as e:
            logger.error(f"TON Monitor Error: {e}")
            await asyncio.sleep(20)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ton_blockchain_monitor())

# --- TELEGRAM WEBHOOK ROUTE ---
@app.post("/webhook")
@app.post("/api/v1/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            text = message.get("text", "")
            username = message.get("from", {}).get("first_name", "Player")

            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == chat_id).first()

            # Handle Referral Code in /start ref_12345
            referrer_id = None
            if text.startswith("/start"):
                parts = text.split()
                if len(parts) > 1 and parts[1].startswith("ref_"):
                    try:
                        referrer_id = int(parts[1].replace("ref_", ""))
                        if referrer_id == chat_id:
                            referrer_id = None # Cannot refer oneself
                    except:
                        referrer_id = None

                # Create New User if Not Exists
                if not user:
                    user = User(
                        telegram_id=chat_id,
                        username=username,
                        balance=0,
                        referrer_id=referrer_id
                    )
                    db.add(user)
                    db.commit()

                    # Award Referrer +50 Coins
                    if referrer_id:
                        ref_user = db.query(User).filter(User.telegram_id == referrer_id).first()
                        if ref_user:
                            ref_user.balance += 50
                            db.commit()
                            ref_msg = (
                                f"👥 <b>New Referral Joined!</b>\n\n"
                                f"User <b>{username}</b> joined using your link!\n"
                                f"🎁 You earned <b>+50 IRAN Coins</b>!"
                            )
                            asyncio.create_task(send_telegram_msg(referrer_id, ref_msg))

                # Send Welcome Message with NEW MINI APP LINK
                welcome_text = (
                    f"🇮🇷 <b>Welcome to IRAN Coin, {username}!</b>\n\n"
                    f"Mine tokens, complete tasks, spin the daily wheel, and upgrade your VIP level to earn real TON rewards!\n\n"
                    f"🪙 <b>Your Balance:</b> {user.balance:,} IRAN Coins\n"
                    f"👑 <b>VIP Status:</b> {user.vip_tier}\n\n"
                    f"Tap the button below to start mining now 👇"
                )

                keyboard = {
                    "inline_keyboard": [[
                        {"text": "🚀 Play IRAN Coin Now", "web_app": {"url": MINI_APP_URL}}
                    ], [
                        {"text": "📢 Official Channel", "url": "https://t.me/IRANCoin_Official"},
                        {"text": "💬 Support Group", "url": "https://t.me/IRANCoinGroup"}
                    ]]
                }
                asyncio.create_task(send_telegram_msg(chat_id, welcome_text, keyboard))

            # --- ADMIN COMMANDS ---
            elif text == "/admin" and chat_id == ADMIN_ID:
                total_users = db.query(User).count()
                total_balance = db.query(User).all()
                total_coins = sum(u.balance for u in total_balance)
                vip_count = db.query(User).filter(User.vip_tier != "Free").count()
                pending_withdraws = db.query(WithdrawalRequest).filter(WithdrawalRequest.status == "Pending").count()

                admin_stats = (
                    f"📊 <b>IRAN COIN SYSTEM STATS</b>\n\n"
                    f"👥 Total Members: <b>{total_users:,}</b>\n"
                    f"🪙 Total Coins Mined: <b>{total_coins:,}</b>\n"
                    f"👑 Total VIP Members: <b>{vip_count}</b>\n"
                    f"💼 Pending Withdrawals: <b>{pending_withdraws}</b>\n\n"
                    f"Use <code>/broadcast Your message</code> to send a message to all members."
                )
                asyncio.create_task(send_telegram_msg(chat_id, admin_stats))

            elif text.startswith("/broadcast") and chat_id == ADMIN_ID:
                bc_text = text.replace("/broadcast", "").strip()
                if bc_text:
                    all_users = db.query(User).all()
                    sent_count = 0
                    for u in all_users:
                        asyncio.create_task(send_telegram_msg(u.telegram_id, f"📢 <b>ANNOUNCEMENT:</b>\n\n{bc_text}"))
                        sent_count += 1
                    asyncio.create_task(send_telegram_msg(ADMIN_ID, f"✅ Broadcast sent to {sent_count} users!"))

            db.close()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook Error: {e}")
        return {"status": "ok"}

# --- API ENDPOINTS FOR MINI APP ---
@app.get("/")
def read_root():
    return {"status": "IRAN Coin Server Running", "app_url": MINI_APP_URL}

@app.get("/api/v1/user/{user_id}")
async def get_user_api(user_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        user = User(telegram_id=user_id, balance=0, vip_tier="Free")
        db.add(user)
        db.commit()
        db.refresh(user)
    
    res = {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "balance": user.balance,
        "vip_tier": user.vip_tier,
        "tap_value": user.tap_value,
        "max_energy": user.max_energy
    }
    db.close()
    return res

class TapModel(BaseModel):
    user_id: int
    count: int

@app.post("/api/v1/tap")
async def tap_coins_api(req: TapModel):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == req.user_id).first()
    if user:
        user.balance += req.count
        db.commit()
    db.close()
    return {"status": "ok"}

class WithdrawModel(BaseModel):
    telegram_id: int
    wallet_address: str
    amount: int

@app.post("/api/v1/withdraw")
async def withdraw_api(req: WithdrawModel):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == req.telegram_id).first()
    if not user or user.balance < req.amount or req.amount < 10000:
        db.close()
        raise HTTPException(status_code=400, detail="Insufficient balance or invalid amount.")

    user.balance -= req.amount
    withdraw = WithdrawalRequest(telegram_id=req.telegram_id, wallet_address=req.wallet_address, amount=req.amount)
    db.add(withdraw)
    db.commit()

    # Alert Admin on Telegram with Approve / Reject details
    admin_text = (
        f"💼 <b>NEW WITHDRAWAL REQUEST!</b>\n\n"
        f"👤 User ID: <code>{req.telegram_id}</code>\n"
        f"🪙 Amount: <b>{req.amount:,} Coins</b>\n"
        f"👛 TON Wallet:\n<code>{req.wallet_address}</code>"
    )
    asyncio.create_task(send_telegram_msg(ADMIN_ID, admin_text))

    db.close()
    return {"status": "success"}

@app.get("/api/v1/ads/watch")
async def ad_watch_api(telegram_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user:
        user.balance += 100
        db.commit()
    db.close()
    return {"status": "rewarded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
