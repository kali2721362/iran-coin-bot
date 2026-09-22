# ==================================================
# ۱. بخش Offerwall Postback (اصلاح‌شده و تمیز)
# ==================================================
@app.api_route("/api/v1/offerwall/postback", methods=["GET", "POST"])
async def offerwall_postback(
    request: Request,
    x_postback_secret: Optional[str] = Header(default=None),
):
    if request.method == "GET":
        params = dict(request.query_params)
    else:
        try:
            params = await request.json()
        except Exception:
            params = dict(request.query_params)

    secret = (params.get("secret") or x_postback_secret or "").strip()
    if OFFERWALL_POSTBACK_SECRET and secret != OFFERWALL_POSTBACK_SECRET:
        raise HTTPException(401, "Invalid secret")

    event_id = str(
        params.get("event_id")
        or params.get("trans_id")
        or params.get("click_id")
        or params.get("conversion_id")
        or ""
    ).strip()
    if not event_id:
        raise HTTPException(400, "event_id/trans_id required")

    try:
        telegram_id = int(
            params.get("telegram_id")
            or params.get("user_id")
            or params.get("sub_id")
            or params.get("subid")
            or params.get("sub")
            or 0
        )
    except (ValueError, TypeError):
        telegram_id = 0

    if not telegram_id:
        raise HTTPException(400, "telegram_id/user_id/sub_id required")

    payout = float(
        params.get("amount_usd")
        or params.get("payout")
        or params.get("amount")
        or 0
    )
    currency = str(params.get("currency") or "USD")
    status = str(params.get("status") or "1")

    if "db_fetchrow" in globals():
        u = await db_fetchrow("SELECT telegram_id FROM users WHERE telegram_id=$1;", telegram_id)
        if not u:
            raise HTTPException(404, "User not found")

        if status == "2":
            return {"success": True, "message": "Reversal received, ignored"}

        exists = await db_fetchrow("SELECT event_id FROM offerwall_events WHERE event_id=$1;", event_id)
        if exists:
            return {"success": True, "message": "Already processed"}

        payout_rate = globals().get("OFFERWALL_PAYOUT_TO_IRAN", 1000.0)
        reward_iran = max(0.0, payout * payout_rate)

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

    return {"success": True, "telegram_id": telegram_id}


# ==================================================
# ۲. بخش چرخونه شانس و آمار کاربر
# ==================================================
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

    coins = 0.0
    ref_count = 0
    last_spin_str = None

    if "db_fetchrow" in globals():
        try:
            row = await db_fetchrow("SELECT balance, last_spin FROM users WHERE telegram_id=$1;", tg_id)
            if row:
                coins = float(row.get("balance") or 0.0)
                last_spin_str = row.get("last_spin")
            
            ref_row = await db_fetchrow("SELECT COUNT(*) as count FROM users WHERE referred_by=$1;", str(tg_id))
            if ref_row:
                ref_count = int(ref_row.get("count") or 0)
        except Exception:
            pass

    can_spin = True
    seconds_left = 0

    if last_spin_str:
        try:
            if isinstance(last_spin_str, str):
                last_spin = datetime.fromisoformat(last_spin_str)
            else:
                last_spin = last_spin_str
            diff = (datetime.utcnow() - last_spin).total_seconds()
            if diff < 86400:
                can_spin = False
                seconds_left = int(86400 - diff)
        except Exception:
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

    coins = 0.0
    last_spin_str = None

    if "db_fetchrow" in globals():
        try:
            row = await db_fetchrow("SELECT balance, last_spin FROM users WHERE telegram_id=$1;", tg_id)
            if row:
                coins = float(row.get("balance") or 0.0)
                last_spin_str = row.get("last_spin")
        except Exception:
            pass

    if last_spin_str:
        try:
            if isinstance(last_spin_str, str):
                last_spin = datetime.fromisoformat(last_spin_str)
            else:
                last_spin = last_spin_str
            if (datetime.utcnow() - last_spin).total_seconds() < 86400:
                raise HTTPException(status_code=400, detail="باید ۲۴ ساعت از چرخش قبلی بگذرد.")
        except HTTPException as e:
            raise e
        except Exception:
            pass

    weights = [r["chance"] for r in SPIN_REWARDS_LIST]
    chosen = random.choices(SPIN_REWARDS_LIST, weights=weights, k=1)[0]
    reward_amount = float(chosen["amount"])
    new_coins = coins + reward_amount
    now_iso = datetime.utcnow().isoformat()

    if "db_exec" in globals():
        try:
            await db_exec("""
                UPDATE users
                SET balance = balance + $1,
                    total_earned = total_earned + $1,
                    last_spin = $2,
                    updated_at = now()
                WHERE telegram_id=$3;
            """, reward_amount, now_iso, tg_id)

            await db_exec("""
                INSERT INTO transactions(telegram_id, type, amount, status, description)
                VALUES($1,'spin',$2,'completed',$3);
            """, tg_id, reward_amount, f"Daily spin reward (+{reward_amount:.0f} IRAN)")
        except Exception:
            try:
                await db_exec("UPDATE users SET balance = balance + $1 WHERE telegram_id=$2;", reward_amount, tg_id)
            except Exception:
                pass

    return {
        "success": True,
        "reward_index": chosen["index"],
        "reward_amount": chosen["amount"],
        "new_balance": new_coins
    }
