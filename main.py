import os
import asyncio
import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_url, create_engine, Column, BigInteger, String, Integer, Float, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")
TON_API_KEY = os.getenv("TONCENTER_API_KEY")
ADMIN_WALLET = os.getenv("ADMIN_WALLET")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- DATABASE MODELS ---
class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    balance = Column(BigInteger, default=0)
    vip_tier = Column(String, default="Free") # Free, Bronze, Silver, Gold, Diamond
    tap_value = Column(Integer, default=1)
    max_energy = Column(Integer, default=1000)
    last_vip_daily_claim = Column(DateTime, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"
    hash = Column(String, primary_key=True) # جلوگیری از تکرار تراکنش
    telegram_id = Column(BigInteger)
    amount = Column(Float)
    tier = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- VIP PRICING & STATS ---
VIP_CONFIG = {
    "Bronze": {"price": 0.1, "tap": 2, "energy": 1500},
    "Silver": {"price": 0.5, "tap": 5, "energy": 3000},
    "Gold": {"price": 1.5, "tap": 10, "energy": 5000},
    "Diamond": {"price": 3.0, "tap": 25, "energy": 10000},
}

# --- BLOCKCHAIN MONITOR ENGINE ---
async def ton_blockchain_monitor():
    """سیستم بررسی خودکار تراکنش های ولت ادمین روی شبکه TON"""
    url = f"https://toncenter.com/api/v2/getTransactions?address={ADMIN_WALLET}&limit=20&api_key={TON_API_KEY}"
    
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        db = SessionLocal()
                        for tx in data["result"]:
                            tx_hash = tx["transaction_id"]["hash"]
                            
                            # اگر این تراکنش قبلاً پردازش نشده باشد
                            if not db.query(Transaction).filter(Transaction.hash == tx_hash).first():
                                msg = tx.get("in_msg", {})
                                comment = msg.get("message", "") # این همان مِموی VIP_Tier_ID است
                                value_nano = int(msg.get("value", 0))
                                value_ton = value_nano / 1e9

                                if comment.startswith("VIP_"):
                                    parts = comment.split("_")
                                    if len(parts) == 3:
                                        tier = parts[1]
                                        user_id = int(parts[2])
                                        
                                        # تایید مبلغ واریزی متناسب با طرح
                                        if tier in VIP_CONFIG and value_ton >= VIP_CONFIG[tier]["price"] * 0.95:
                                            # ۱. ثبت تراکنش
                                            new_tx = Transaction(hash=tx_hash, telegram_id=user_id, amount=value_ton, tier=tier)
                                            db.add(new_tx)
                                            
                                            # ۲. آپدیت لول کاربر
                                            user = db.query(User).filter(User.telegram_id == user_id).first()
                                            if user:
                                                user.vip_tier = tier
                                                user.tap_value = VIP_CONFIG[tier]["tap"]
                                                user.max_energy = VIP_CONFIG[tier]["energy"]
                                                print(f"✅ VIP {tier} activated for user {user_id}")
                                            
                                            db.commit()
                        db.close()
            await asyncio.sleep(60) # هر یک دقیقه چک کن
        except Exception as e:
            print(f"Monitor Error: {e}")
            await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ton_blockchain_monitor())

# --- API ROUTES FOR MINI APP ---

@app.get("/api/v1/user/{user_id}")
async def get_user(user_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == user_id).first()
    if not user:
        user = User(telegram_id=user_id, balance=0, vip_tier="Free")
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user

class TapRequest(BaseModel):
    user_id: int
    count: int

@app.post("/api/v1/tap")
async def tap_coins(req: TapRequest):
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == req.user_id).first()
    if user:
        # اینجا میتوان چک کرد که تقلب نشود (مثلا بررسی تعداد تپ در ثانیه)
        user.balance += req.count
        db.commit()
    db.close()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
