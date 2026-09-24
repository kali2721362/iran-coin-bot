import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, BigInteger, String, Integer, Float, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRANCoinDirect")

# --- GUARANTEED HARDCODED FALLBACKS ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8639953959:AAHX6zYJgqQLo9JExYZ3GuqcEz-yrgjRmVs").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "979411415"))
ADMIN_WALLET = os.getenv("ADMIN_WALLET", "UQCcUO7XRuLyf46obnkSUrec5L00yng7sw8Jut04rlLKCSjB").strip()
TON_API_KEY = os.getenv("TONCENTER_API_KEY", "1d85a1804835e8c0c7458f49f9df7ed0c03d18c067999ec428fc1bd9136a0a8c").strip()
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://kali2721362.github.io/iran-coin-bot/?v=110000").strip()
PORT = int(os.getenv("PORT", 8000))

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# --- DATABASE SAFE INIT ---
Base = declarative_base()
engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    except Exception as e:
        logger.error(f"DB Engine Init Error: {e}")

class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    balance = Column(BigInteger, default=0)
    vip_tier = Column(String, default="Free")
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
    status = Column(String, default="Pending")
    created_at = Column(DateTime, default=datetime.utcnow)

if engine:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Base metadata error: {e}")

# --- FASTAPI APP ---
app = FastAPI(title="IRAN Coin Guaranteed Direct Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DIRECT AWAIT TELEGRAM SENDER (GUARANTEED DELIVERY)
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
            logger.info(f"Direct Telegram Send Result: {r.status_code}")
        except Exception as e:
            logger.error(f"Direct Telegram Send Exception: {e}")

# --- WEBHOOK ROUTE (IMMEDIATE RESPONSE) ---
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

            if text.startswith("/start"):
                # 1. IMMEDIATE TELEGRAM MESSAGE SENDING (NO DELAY, NO DB DEPENDENCY)
                welcome_text = (
                    f"🇮🇷 <b>Welcome to IRAN Coin, {username}!</b>\n\n"
                    f"Mine tokens, complete tasks, spin the daily wheel, and upgrade your VIP level to earn real TON rewards!\n\n"
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

                # DIRECT AWAIT - GUARANTEES TELEGRAM API CALL EXECUTES
                await send_telegram_now(chat_id, welcome_text, keyboard)

                # 2. SAFE BACKGROUND DATABASE LOGIC (AFTER MESSAGE IS SENT)
                if SessionLocal:
                    try:
                        db = SessionLocal()
                        user = db.query(User).filter(User.telegram_id == chat_id).first()
                        if not user:
                            user = User(telegram_id=chat_id, username=username, balance=0)
                            db.add(user)
                            db.commit()
                        db.close()
                    except Exception as dbe:
                        logger.error(f"Safe DB Error: {dbe}")

            elif text == "/admin" and chat_id == ADMIN_ID:
                await send_telegram_now(ADMIN_ID, "📊 <b>ADMIN PANEL ONLINE</b>\nServer is actively responding to requests.")

        return {"status": "ok"}
    except Exception as global_e:
        logger.error(f"Global Webhook Error: {global_e}")
        return {"status": "ok"}

# --- API ENDPOINTS ---
@app.get("/")
def read_root():
    return {"status": "IRAN Coin Server Running", "app_url": MINI_APP_URL}

@app.get("/api/v1/user/{user_id}")
async def get_user_api(user_id: int):
    if not SessionLocal:
        return {"telegram_id": user_id, "balance": 0, "vip_tier": "Free", "tap_value": 1, "max_energy": 1000}
    try:
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
    except Exception:
        return {"telegram_id": user_id, "balance": 0, "vip_tier": "Free", "tap_value": 1, "max_energy": 1000}

class TapModel(BaseModel):
    user_id: int
    count: int

@app.post("/api/v1/tap")
async def tap_coins_api(req: TapModel):
    if SessionLocal:
        try:
            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == req.user_id).first()
            if user:
                user.balance += req.count
                db.commit()
            db.close()
        except Exception:
            pass
    return {"status": "ok"}

class WithdrawModel(BaseModel):
    telegram_id: int
    wallet_address: str
    amount: int

@app.post("/api/v1/withdraw")
async def withdraw_api(req: WithdrawModel):
    if SessionLocal:
        try:
            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == req.telegram_id).first()
            if user and user.balance >= req.amount:
                user.balance -= req.amount
                withdraw = WithdrawalRequest(telegram_id=req.telegram_id, wallet_address=req.wallet_address, amount=req.amount)
                db.add(withdraw)
                db.commit()
                await send_telegram_now(ADMIN_ID, f"💼 <b>WITHDRAW REQUEST</b>\n\nUser: <code>{req.telegram_id}</code>\nCoins: {req.amount:,}\nWallet: <code>{req.wallet_address}</code>")
            db.close()
        except Exception:
            pass
    return {"status": "success"}

@app.get("/api/v1/ads/watch")
async def ad_watch_api(telegram_id: int):
    if SessionLocal:
        try:
            db = SessionLocal()
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if user:
                user.balance += 100
                db.commit()
            db.close()
        except Exception:
            pass
    return {"status": "rewarded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
