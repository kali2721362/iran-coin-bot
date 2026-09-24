import os
import asyncio
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, BigInteger, String, Integer, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# --- CONFIGURATION ---
# Railway به صورت خودکار DATABASE_URL را می دهد
DB_URL = os.getenv("DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

TON_API_KEY = os.getenv("TONCENTER_API_KEY")
ADMIN_WALLET = os.getenv("ADMIN_WALLET")
PORT = int(os.environ.get("PORT", 8000)) # دریافت پورت از Railway

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Base = declarative_base()
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- DATABASE MODELS ---
class User(Base):
    __tablename__ = "users"
    telegram_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    balance = Column(BigInteger, default=0)
    vip_tier = Column(String, default="Free")
    tap_value = Column(Integer, default=1)
    max_energy = Column(Integer, default=1000)

class Transaction(Base):
    __tablename__ = "transactions"
    hash = Column(String, primary_key=True)
    telegram_id = Column(BigInteger)
    amount = Column(Float)
    tier = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

VIP_CONFIG = {
    "Bronze": {"price": 0.1, "tap": 2, "energy": 1500},
    "Silver": {"price": 0.5, "tap": 5, "energy": 3000},
    "Gold": {"price": 1.5, "tap": 10, "energy": 5000},
    "Diamond": {"price": 3.0, "tap": 25, "energy": 10000},
}

# --- BLOCKCHAIN MONITOR ---
async def ton_blockchain_monitor():
    url = f"https://toncenter.com/api/v2/getTransactions?address={ADMIN_WALLET}&limit=20&api_key={TON_API_KEY}"
    while True:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ok"):
                        db = SessionLocal()
                        for tx in data["result"]:
                            tx_hash = tx["transaction_id"]["hash"]
                            if not db.query(Transaction).filter(Transaction.hash == tx_hash).first():
                                msg = tx.get("in_msg", {})
                                comment = msg.get("message", "")
                                value_ton = int(msg.get("value", 0)) / 1e9
                                if comment.startswith("VIP_"):
                                    parts = comment.split("_")
                                    if len(parts) == 3:
                                        tier = parts[1]
                                        user_id = int(parts[2])
                                        if tier in VIP_CONFIG and value_ton >= VIP_CONFIG[tier]["price"] * 0.9:
                                            new_tx = Transaction(hash=tx_hash, telegram_id=user_id, amount=value_ton, tier=tier)
                                            db.add(new_tx)
                                            user = db.query(User).filter(User.telegram_id == user_id).first()
                                            if user:
                                                user.vip_tier = tier
                                                user.tap_value = VIP_CONFIG[tier]["tap"]
                                                user.max_energy = VIP_CONFIG[tier]["energy"]
                                            db.commit()
                        db.close()
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Monitor Error: {e}")
            await asyncio.sleep(30)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(ton_blockchain_monitor())

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
        user.balance += req.count
        db.commit()
    db.close()
    return {"status": "ok"}

@app.get("/")
def read_root():
    return {"status": "IRAN Coin Server Running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
