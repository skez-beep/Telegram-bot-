import json
import os
from datetime import datetime, timedelta, time

import requests
from telegram import LabeledPrice, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

# =========================
# إعدادات
# =========================
TOKEN =("8749740785:AAEAg9F4GxOAAAdkDfTWdpH2u3F-leRxw8Q")
if not TOKEN:
    raise ValueError("TOKEN not found in environment variables")

ADMIN_ID = 5322650589
VIP_USERS = [5322650589]  # حسابك بدون حد
CONTACT_USERNAME = "@Abod_gold"
BOT_NAME = "Gold⚜️ TRADING"

DATA_FILE = "data.json"

# بدّلنا المصدر إلى XAUUSD spot على Yahoo
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X"

MONTHLY_VIP_STARS = 500

AUTO_SIGNAL_TIMES = [
    time(hour=13, minute=0, second=0),
    time(hour=17, minute=0, second=0),
]

# =========================
# تخزين البيانات
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data:
                data["users"] = {}
            return data
    except Exception:
        return {"users": {}}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


db = load_data()


def get_user_record(user_id: int):
    uid = str(user_id)
    users = db["users"]

    if uid not in users:
        users[uid] = {
            "username": "",
            "first_name": "",
            "joined_at": datetime.now().isoformat(),
            "free_total_used": 0,
            "vip_until": None,
            "last_signal_day": "",
            "received_today": 0,
            "blocked": False,
        }
        save_data(db)

    return users[uid]


def is_unlimited_user(user_id: int) -> bool:
    return user_id == ADMIN_ID or user_id in VIP_USERS


def is_vip_active(user_id: int, user_data: dict) -> bool:
    if is_unlimited_user(user_id):
        return True

    vip_until = user_data.get("vip_until")
    if not vip_until:
        return False

    try:
        return datetime.now() < datetime.fromisoformat(vip_until)
    except Exception:
        return False


def extend_vip_days(user_id: int, days: int):
    rec = get_user_record(user_id)
    now = datetime.now()

    current_end = None
    if rec.get("vip_until"):
        try:
            current_end = datetime.fromisoformat(rec["vip_until"])
        except Exception:
            current_end = None

    if current_end and current_end > now:
        new_end = current_end + timedelta(days=days)
    else:
        new_end = now + timedelta(days=days)

    rec["vip_until"] = new_end.isoformat()
    save_data(db)
    return new_end


def reset_daily_if_needed(user_data: dict):
    today = datetime.now().date().isoformat()
    if user_data.get("last_signal_day") != today:
        user_data["last_signal_day"] = today
        user_data["received_today"] = 0


def can_receive_signal(user_id: int, user_data: dict) -> bool:
    if user_data.get("blocked"):
        return False

    if is_unlimited_user(user_id):
        return True

    reset_daily_if_needed(user_data)

    if user_data["received_today"] >= 2:
        return False

    if is_vip_active(user_id, user_data):
        return True

    return user_data["free_total_used"] < 2


def mark_signal_sent(user_id: int, user_data: dict):
    if is_unlimited_user(user_id):
        return

    reset_daily_if_needed(user_data)
    user_data["received_today"] += 1

    if not is_vip_active(user_id, user_data):
        user_data["free_total_used"] += 1


# =========================
# السوق
# =========================
def fetch_gold_chart(range_value="5d", interval="15m"):
    params = {
        "range": range_value,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits,capitalGains",
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(YAHOO_URL, params=params, headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()

    if "chart" not in data or not data["chart"].get("result"):
        raise ValueError("لم يتم استلام بيانات السوق")

    result = data["chart"]["result"][0]
    meta = result.get("meta", {})
    indicators = result.get("indicators", {})
    quotes = indicators.get("quote", [])

    if not quotes:
        raise ValueError("لا توجد بيانات quote")

    quote = quotes[0]

    closes = quote.get("close", [])
    opens = quote.get("open", [])
    highs = quote.get("high", [])
    lows = quote.get("low", [])
    timestamps = result.get("timestamp", [])

    candles = []
    for i in range(len(closes)):
        c = closes[i]
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        t = timestamps[i] if i < len(timestamps) else None

        if c is None or o is None or h is None or l is None or t is None:
            continue

        candles.append(
            {
                "time": t,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
            }
        )

    if len(candles) < 50:
        raise ValueError("البيانات غير كافية للتحليل")

    current_price = meta.get("regularMarketPrice")
    previous_close = meta.get("previousClose")

    if current_price is None:
        current_price = candles[-1]["close"]
    if previous_close is None:
        previous_close = candles[-2]["close"]

    return {
        "price": float(current_price),
        "prev_close": float(previous_close),
        "currency": meta.get("currency", "USD"),
        "symbol": meta.get("symbol", "XAUUSD=X"),
        "candles": candles,
    }


# =========================
# مؤشرات
# =========================
def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    ema_value = sum(values[:period]) / period

    for price in values[period:]:
        ema_value = (price * k) + (ema_value * (1 - k))

    return ema_value


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        gain = max(diff, 0)
        loss = abs(min(diff, 0))

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr_value = sum(true_ranges[:period]) / period

    for tr in true_ranges[period:]:
        atr_value = ((atr_value * (period - 1)) + tr) / period

    return atr_value


def adx(candles, period=14):
    if len(candles) < period + 2:
        return None

    trs = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, len(candles)):
        curr = candles[i]
        prev = candles[i - 1]

        up_move = curr["high"] - prev["high"]
        down_move = prev["low"] - curr["low"]

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0

        tr = max(
            curr["high"] - curr["low"],
            abs(curr["high"] - prev["close"]),
            abs(curr["low"] - prev["close"])
        )

        trs.append(tr)
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)

    if len(trs) < period:
        return None

    atr_sum = sum(trs[:period])
    plus_dm_sum = sum(plus_dm_list[:period])
    minus_dm_sum = sum(minus_dm_list[:period])

    dx_values = []

    for i in range(period, len(trs)):
        if i > period:
            atr_sum = atr_sum - (atr_sum / period) + trs[i]
            plus_dm_sum = plus_dm_sum - (plus_dm_sum / period) + plus_dm_list[i]
            minus_dm_sum = minus_dm_sum - (minus_dm_sum / period) + minus_dm_list[i]

        if atr_sum == 0:
            continue

        plus_di = 100 * (plus_dm_sum / atr_sum)
        minus_di = 100 * (minus_dm_sum / atr_sum)

        if (plus_di + minus_di) == 0:
            continue

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        dx_values.append(dx)

    if len(dx_values) < period:
        return None

    adx_value = sum(dx_values[:period]) / period

    for dx in dx_values[period:]:
        adx_value = ((adx_value * (period - 1)) + dx) / period

    return adx_value


# =========================
# التحليل
# =========================
def build_signal():
    market = fetch_gold_chart(range_value="5d", interval="15m")
    candles = market["candles"]
    closes = [c["close"] for c in candles]

    current_price = closes[-1]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)
    atr14 = atr(candles, 14)
    adx14 = adx(candles, 14)

    if None in [ema9, ema21, rsi14, atr14, adx14]:
        raise ValueError("المؤشرات غير جاهزة")

    direction = "WAIT"
    reasons = []

    buy_setup = (
        ema9 > ema21 and
        adx14 >= 20 and
        40 <= rsi14 <= 52 and
        current_price > ema21
    )

    sell_setup = (
        ema9 < ema21 and
        adx14 >= 20 and
        48 <= rsi14 <= 60 and
        current_price < ema21
    )

    if buy_setup:
        direction = "BUY"
        reasons.append("الترند صاعد: EMA9 فوق EMA21")
        reasons.append("فيه قوة ترند: ADX فوق 20")
        reasons.append("هبوط نسبي مناسب للشراء")
        reasons.append("السعر فوق EMA21")
    elif sell_setup:
        direction = "SELL"
        reasons.append("الترند هابط: EMA9 تحت EMA21")
        reasons.append("فيه قوة ترند: ADX فوق 20")
        reasons.append("صعود نسبي مناسب للبيع")
        reasons.append("السعر تحت EMA21")
    else:
        reasons.append("ما فيه setup قوي الآن")
        reasons.append("البوت يتجنب الدخول الضعيف")

    entry = round(current_price, 2)

    if direction == "BUY":
        sl = round(entry - (atr14 * 1.2), 2)
        tp1 = round(entry + (atr14 * 1.5), 2)
        tp2 = round(entry + (atr14 * 2.2), 2)
    elif direction == "SELL":
        sl = round(entry + (atr14 * 1.2), 2)
        tp1 = round(entry - (atr14 * 1.5), 2)
        tp2 = round(entry - (atr14 * 2.2), 2)
    else:
        sl = None
        tp1 = None
        tp2 = None

    return {
        "symbol": market["symbol"],
        "currency": market["currency"],
        "price": round(current_price, 2),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "rsi14": round(rsi14, 2),
        "atr14": round(atr14, 2),
        "adx14": round(adx14, 2),
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "reason": reasons,
    }


def format_signal(sig: dict) -> str:
    if sig["direction"] == "WAIT":
        return (
            f"📊 تحليل الذهب\n\n"
            f"🟡 السعر: {sig['price']} {sig['currency']}\n"
            f"📈 EMA9: {sig['ema9']}\n"
            f"📉 EMA21: {sig['ema21']}\n"
            f"📍 RSI14: {sig['rsi14']}\n"
            f"💪 ADX14: {sig['adx14']}\n"
            f"📏 ATR14: {sig['atr14']}\n\n"
            f"⏳ لا توجد صفقة قوية الآن\n"
            f"🧠 السبب:\n- " + "\n- ".join(sig["reason"]) + f"\n\n📩 {CONTACT_USERNAME}"
        )

    arrow = "📈" if sig["direction"] == "BUY" else "📉"
    side = "شراء" if sig["direction"] == "BUY" else "بيع"

    return (
        f"📊 إشارة ذهب قوية\n\n"
        f"{arrow} {side} GOLD\n"
        f"🟡 الدخول: {sig['entry']} {sig['currency']}\n"
        f"🎯 الهدف 1: {sig['tp1']} {sig['currency']}\n"
        f"🎯 الهدف 2: {sig['tp2']} {sig['currency']}\n"
        f"🛑 الوقف: {sig['sl']} {sig['currency']}\n\n"
        f"📈 EMA9: {sig['ema9']}\n"
        f"📉 EMA21: {sig['ema21']}\n"
        f"📍 RSI14: {sig['rsi14']}\n"
        f"💪 ADX14: {sig['adx14']}\n"
        f"📏 ATR14: {sig['atr14']}\n\n"
        f"🧠 السبب:\n- " + "\n- ".join(sig["reason"]) + f"\n\n📩 {CONTACT_USERNAME}"
    )


# =========================
# أوامر
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rec = get_user_record(user.id)
    rec["username"] = f"@{user.username}" if user.username else ""
    rec["first_name"] = user.first_name or ""
    save_data(db)

    text = (
        f"🔥 أهلاً بك في {BOT_NAME} 🔥\n\n"
        f"✅ السعر صار XAUUSD\n"
        f"✅ تحليل ذهب حقيقي\n"
        f"✅ صفقتان تلقائياً يومياً\n"
        f"✅ أول صفقتين مجاناً ثم VIP شهري\n\n"
        f"الأوامر:\n"
        f"/price - سعر الذهب الآن\n"
        f"/signal - تحليل يدوي الآن\n"
        f"/status - وضع حسابك\n"
        f"/buyvip - شراء VIP شهر\n"
        f"/vip - معلومات الاشتراك\n"
        f"/myid - إظهار ID\n"
        f"/support - الدعم\n"
        f"/terms - الشروط\n\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID تبعك: {update.effective_user.id}")


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📩 الدعم الفني والتواصل: {CONTACT_USERNAME}")


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 الشروط\n\n"
        "1) الإشارات تحليلية وليست ضمان ربح.\n"
        "2) الاشتراك VIP مدته 30 يوم.\n"
        "3) لا يوجد استرجاع بعد التفعيل.\n"
        "4) المستخدم مسؤول عن قراراته المالية.\n"
        f"5) الدعم: {CONTACT_USERNAME}"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rec = get_user_record(user_id)
    reset_daily_if_needed(rec)
    save_data(db)

    vip_text = "نعم ✅" if is_vip_active(user_id, rec) else "لا ❌"
    vip_until = "دائم ♾️" if is_unlimited_user(user_id) else (rec["vip_until"] or "غير مفعل")

    text = (
        f"📋 حالة الحساب\n\n"
        f"🎁 الصفقات المجانية المستخدمة: {rec['free_total_used']} / 2\n"
        f"📨 إشارات اليوم المستلمة: {rec['received_today']} / 2\n"
        f"💎 VIP: {vip_text}\n"
        f"📅 نهاية الاشتراك: {vip_until}\n\n"
        f"📩 {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        market = fetch_gold_chart(range_value="1d", interval="5m")
        change = round(market["price"] - market["prev_close"], 2)
        icon = "📈" if change >= 0 else "📉"

        text = (
            f"📊 سعر الذهب الآن\n\n"
            f"🟡 الرمز: {market['symbol']}\n"
            f"💰 السعر: {market['price']} {market['currency']}\n"
            f"{icon} التغير: {change}\n\n"
            f"📩 {CONTACT_USERNAME}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        print("PRICE ERROR:", e)
        await update.message.reply_text("❌ فشل جلب السعر حالياً")


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rec = get_user_record(user_id)

    if not can_receive_signal(user_id, rec):
        if rec["received_today"] >= 2:
            await update.message.reply_text(
                f"⛔ وصلت الحد اليومي: صفقتان فقط.\n\n"
                f"📩 VIP: {CONTACT_USERNAME}"
            )
            return

        if not is_vip_active(user_id, rec) and rec["free_total_used"] >= 2:
            await update.message.reply_text(
                f"⛔ انتهت أول صفقتين مجاناً.\n"
                f"💎 للاشتراك VIP: {CONTACT_USERNAME}"
            )
            return

        await update.message.reply_text("⛔ لا يمكنك استلام صفقة الآن")
        return

    try:
        sig = build_signal()
        mark_signal_sent(user_id, rec)
        save_data(db)
        await update.message.reply_text(format_signal(sig))
    except Exception as e:
        print("SIGNAL ERROR:", e)
        await update.message.reply_text("❌ فشل التحليل حالياً، حاول لاحقاً")


async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"💎 اشتراك VIP الشهري\n\n"
        f"✔ مدة الاشتراك: 30 يوم\n"
        f"✔ استلام الإشارات بعد انتهاء المجاني\n"
        f"✔ الإشارات التلقائية تبقى شغالة\n\n"
        f"💰 السعر: {MONTHLY_VIP_STARS} Stars\n"
        f"🛒 للشراء: /buyvip\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def buyvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    title = "VIP شهر واحد"
    description = "اشتراك VIP لمدة 30 يوم في بوت إشارات الذهب"
    payload = f"vip_30d_{update.effective_user.id}_{int(datetime.now().timestamp())}"
    currency = "XTR"
    prices = [LabeledPrice("VIP 30 Days", MONTHLY_VIP_STARS)]

    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency=currency,
            prices=prices,
        )
    except Exception as e:
        print("INVOICE ERROR:", e)
        await update.message.reply_text("❌ فشل إنشاء فاتورة الدفع حالياً")


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query:
        return

    try:
        await query.answer(ok=True)
    except Exception as e:
        print("PRECHECKOUT ERROR:", e)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.successful_payment:
        return

    user = update.effective_user
    new_end = extend_vip_days(user.id, 30)

    await update.message.reply_text(
        f"✅ تم تفعيل VIP بنجاح\n"
        f"📅 حتى: {new_end.strftime('%Y-%m-%d %H:%M')}\n"
        f"📩 الدعم: {CONTACT_USERNAME}"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"💰 دفعة جديدة\n"
                f"👤 المستخدم: {user.first_name}\n"
                f"🆔 ID: {user.id}\n"
                f"📅 تم تمديد VIP حتى: {new_end.strftime('%Y-%m-%d %H:%M')}"
            ),
        )
    except Exception as e:
        print("ADMIN NOTIFY ERROR:", e)


async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("استعمال الأمر:\n/addvip USER_ID DAYS")
        return

    try:
        target_user_id = int(context.args[0])
        days = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ USER_ID و DAYS يجب أن يكونوا أرقام")
        return

    new_end = extend_vip_days(target_user_id, days)
    await update.message.reply_text(
        f"✅ تم تفعيل VIP للمستخدم {target_user_id}\n"
        f"📅 حتى: {new_end.strftime('%Y-%m-%d %H:%M')}"
    )


async def delvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text("استعمال الأمر:\n/delvip USER_ID")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ USER_ID يجب أن يكون رقم")
        return

    rec = get_user_record(target_user_id)
    rec["vip_until"] = None
    save_data(db)

    await update.message.reply_text(f"✅ تم حذف VIP عن {target_user_id}")


async def auto_signal(context: ContextTypes.DEFAULT_TYPE):
    try:
        sig = build_signal()
    except Exception as e:
        print("AUTO SIGNAL BUILD ERROR:", e)
        return

    if sig["direction"] == "WAIT":
        print("AUTO SIGNAL SKIPPED: WAIT")
        return

    text = format_signal(sig)
    sent_count = 0

    for uid, rec in db["users"].items():
        try:
            user_id = int(uid)

            if not can_receive_signal(user_id, rec):
                continue

            await context.bot.send_message(chat_id=user_id, text=text)
            mark_signal_sent(user_id, rec)
            sent_count += 1
        except Exception as e:
            print(f"SEND ERROR {uid}: {e}")

    save_data(db)
    print(f"Auto signal sent to {sent_count} users")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("support", support))
    app.add_handler(CommandHandler("terms", terms))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("vip", vip))
    app.add_handler(CommandHandler("buyvip", buyvip))
    app.add_handler(CommandHandler("addvip", addvip))
    app.add_handler(CommandHandler("delvip", delvip))

    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    for i, signal_time in enumerate(AUTO_SIGNAL_TIMES, start=1):
        app.job_queue.run_daily(auto_signal, time=signal_time, name=f"auto_signal_{i}")

    print("🔥 Bot running Abod...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
