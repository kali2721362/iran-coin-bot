@@ -560,7 +560,7 @@ async def offerwall_postback(
    request: Request,
    x_postback_secret: str | None = Header(default=None),
):
    # Accept params from query OR json body
    # Read params from query (GET) or JSON body (POST)
    if request.method == "GET":
        params = dict(request.query_params)
    else:
@@ -569,27 +569,83 @@ async def offerwall_postback(
        except:
            params = dict(request.query_params)

    # Secret check
    # Secret check (query ?secret=... OR header X-Postback-Secret)
    secret = (params.get("secret") or x_postback_secret or "").strip()
    if OFFERWALL_POSTBACK_SECRET and secret != OFFERWALL_POSTBACK_SECRET:
        raise HTTPException(401, "Invalid secret")

    event_id = str(params.get("event_id") or params.get("click_id") or params.get("conversion_id") or "")
    # CPX compatibility:
    # event id can be trans_id, click_id, conversion_id...
    event_id = str(
        params.get("event_id")
        or params.get("trans_id")
        or params.get("click_id")
        or params.get("conversion_id")
        or ""
    ).strip()
    if not event_id:
        raise HTTPException(400, "event_id required")

    telegram_id = int(params.get("telegram_id") or params.get("sub_id") or params.get("sub") or 0)
        raise HTTPException(400, "event_id/trans_id required")

    # user id can be user_id or sub_id etc.
    telegram_id = int(
        params.get("telegram_id")
        or params.get("user_id")
        or params.get("sub_id")
        or params.get("subid")
        or params.get("sub")
        or 0
    )
    if not telegram_id:
        raise HTTPException(400, "telegram_id/sub_id required")
        raise HTTPException(400, "telegram_id/user_id/sub_id required")

    # payout can be amount_usd (CPX) or payout/amount
    payout = float(
        params.get("amount_usd")
        or params.get("payout")
        or params.get("amount")
        or 0
    )

    payout = float(params.get("payout") or params.get("amount") or 0)
    currency = str(params.get("currency") or "USD")
    status = str(params.get("status") or "1")  # CPX: 1=pending/approved, 2=reversed

    # Ensure user exists
    u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        raise HTTPException(404, "User not found")

    # If reversed -> (مرحله بعدی) می‌تونیم برگشت امتیاز هم اضافه کنیم
    if status == "2":
        # For now, ignore reversals safely (no extra reward)
        return {"success": True, "message": "Reversal received, ignored (not implemented)"}

    # idempotency: ignore if already processed
    # Idempotency: if already processed, ignore
    exists = await db_fetchrow("SELECT event_id FROM offerwall_events WHERE event_id=$1;", event_id)
    if exists:
        return {"success": True, "message": "Already processed"}

    reward_iran = max(0.0, payout * OFFERWALL_PAYOUT_TO_IRAN)

    await db_exec("""
        INSERT INTO offerwall_events(event_id, telegram_id, payout, reward_iran, currency, raw)
        VALUES($1,$2,$3,$4,$5,$6);
    """, event_id, telegram_id, payout, reward_iran, currency, str(params)[:5000])

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

    return {"success": True, "telegram_id": telegram_id, "reward_iran": reward_iran, "status": status}

    # user must exist
    u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
    if not u:
        
# ==================================================
# کد چرخونه روزانه و آمار کاربر (انتهای فایل)
# ==================================================
import random
from datetime import datetime

SPIN_REWARDS_LIST = [
    {"index": 0, "amount": 50,   "label": "50",   "chance": 35},
    {"index": 1, "amount": 100,  "label": "100",  "chance": 25},
    {"index": 2, "amount": 250,  "label": "250",  "chance": 18},
    {"index": 3, "amount": 500,  "label": "500",  "chance": 12},
    {"index": 4, "amount": 1000, "label": "1,000", "chance": 7},
    {"index": 5, "amount": 2500, "label": "2,500", "chance": 3},
]

@app.get("/api/v1/user/stats/{telegram_id}")
async def get_user_stats_api(telegram_id: str):
    try:
        tg_id = int(telegram_id)
    except:
        tg_id = 111111

    user = None
    if "get_user" in globals():
        try: user = await get_user(tg_id)
        except: pass
    
    coins = user.get("balance", user.get("coins", 0)) if user else 0
    ref_count = user.get("referrals_count", user.get("ref_count", 0)) if user else 0
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
        "telegram_id": tg_id,
        "coins": coins,
        "referrals_count": ref_count,
        "can_spin": can_spin,
        "seconds_to_next_spin": seconds_left
    }

@app.post("/api/v1/spin/{telegram_id}")
async def process_spin_api(telegram_id: str):
    try:
        tg_id = int(telegram_id)
    except:
        tg_id = 111111

    user = None
    if "get_user" in globals():
        try: user = await get_user(tg_id)
        except: pass
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

    weights = [r["chance"] for r in SPIN_REWARDS_LIST]
    chosen = random.choices(SPIN_REWARDS_LIST, weights=weights, k=1)[0]

    current_coins = user.get("balance", user.get("coins", 0))
    new_coins = current_coins + chosen["amount"]
    now_iso = datetime.utcnow().isoformat()

    if "update_user" in globals():
        try: await update_user(tg_id, {"balance": new_coins, "coins": new_coins, "last_spin": now_iso})
        except: pass

    return {
        "success": True,
        "reward_index": chosen["index"],
        "reward_amount": chosen["amount"],
        "new_balance": new_coins
    }
