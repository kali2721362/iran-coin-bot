# ==================================================
# API چرخونه روزانه (Daily Spin) و آمار کاربر
# ==================================================
import random
from datetime import datetime
from fastapi import HTTPException

SPIN_REWARDS = [
    {"index": 0, "amount": 50,   "label": "50",   "chance": 35},   # ۳۵٪ شانس
    {"index": 1, "amount": 100,  "label": "100",  "chance": 25},   # ۲۵٪ شانس
    {"index": 2, "amount": 250,  "label": "250",  "chance": 18},   # ۱۸٪ شانس
    {"index": 3, "amount": 500,  "label": "500",  "chance": 12},   # ۱۲٪ شانس
    {"index": 4, "amount": 1000, "label": "1,000", "chance": 7},   # ۷٪ شانس
    {"index": 5, "amount": 2500, "label": "2,500", "chance": 3},   # ۳٪ شانس
]

@app.get("/api/v1/user/stats/{telegram_id}")
async def get_user_stats(telegram_id: str):
    try:
        tg_id = int(telegram_id)
    except:
        tg_id = telegram_id

    user = None
    if "get_user" in globals():
        user = await get_user(tg_id)
    
    coins = user.get("coins", 0) if user else 0
    ref_count = user.get("referrals_count", 0) if user else 0
    last_spin_str = user.get("last_spin") if user else None

    can_spin = True
    seconds_left = 0

    if last_spin_str:
        try:
            last_spin = datetime.fromisoformat(str(last_spin_str))
            diff = (datetime.utcnow() - last_spin).total_seconds()
            if diff < 86400:
                can_spin = False
                seconds_left = int(86400 - diff)
        except:
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
    try:
        tg_id = int(telegram_id)
    except:
        tg_id = telegram_id

    user = None
    if "get_user" in globals():
        user = await get_user(tg_id)
    if not user:
        user = {}

    last_spin_str = user.get("last_spin")
    if last_spin_str:
        try:
            last_spin = datetime.fromisoformat(str(last_spin_str))
            if (datetime.utcnow() - last_spin).total_seconds() < 86400:
                raise HTTPException(status_code=400, detail="باید ۲۴ ساعت از چرخش قبلی بگذرد.")
        except HTTPException as e:
            raise e
        except:
            pass

    weights = [r["chance"] for r in SPIN_REWARDS]
    chosen = random.choices(SPIN_REWARDS, weights=weights, k=1)[0]

    current_coins = user.get("coins", 0)
    new_coins = current_coins + chosen["amount"]
    now_iso = datetime.utcnow().isoformat()

    if "update_user" in globals():
        await update_user(tg_id, {"coins": new_coins, "last_spin": now_iso})
    elif "add_user_coins" in globals():
        await add_user_coins(tg_id, chosen["amount"])

    return {
        "success": True,
        "reward_index": chosen["index"],
        "reward_amount": chosen["amount"],
        "new_balance": new_coins
    }
