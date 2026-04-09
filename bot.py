import json
import os
import requests
from datetime import datetime, timedelta, time

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8749740785:AAFV0BadXSQr2uufWn30dJEd8IHrxH_A8Ng"
ADMIN_ID = 5322650589
VIP_USERS = [5322650589]
CONTACT_USERNAME = "@Abod_gold"
BOT_NAME = "Gold⚜️ TRADING"
DATA_FILE = "data.json"

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"


# =========================
# البيانات
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
    if uid not in db["users"]:
        db["users"][uid] = {
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
    return db["users"][uid]


def is_vip_active(user_data: dict) -> bool:
    vip_until = user_data.get("vip_until")
    if not vip_until:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(vip_until)
    except Exception:
        return False


def reset_daily_if_needed(user_data: dict):
    today = datetime.now().date().isoformat()
    if user_data.get("last_signal_day") != today:
        user_data["last_signal_day"] = today
        user_data["received_today"] = 0


def can_receive_signal(user_data: dict) -> bool:
    if user_data.get("blocked"):
        return False

    reset_daily_if_needed(user_data)

    if user_data["received_today"] >= 2:
        return False

    if is_vip_active(user_data):
        return True

    return user_data["free_total_used"] < 2


def mark_signal_sent(user_data: dict):
    reset_daily_if_needed(user_data)
    user_data["received_today"] += 1

    if not is_vip_active(user_data):
        user_data["free_total_used"] += 1


# =========================
# السوق والتحليل
# =========================
def fetch_gold_chart(range_value="5d", interval="15m"):
    params = {
        "range": range_value,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits,capitalGains",
    }
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

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

        candles.append({
            "time": t,
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
        })

    if len(candles) < 30:
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
        "symbol": meta.get("symbol", "GC=F"),
        "candles": candles,
    }


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


def build_signal():
    market = fetch_gold_chart(range_value="5d", interval="15m")
    candles = market["candles"]
    closes = [c["close"] for c in candles]
    last = candles[-1]
    prev = candles[-2]

    current_price = closes[-1]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi14 = rsi(closes, 14)

    if ema9 is None or ema21 is None or rsi14 is None:
        raise ValueError("المؤشرات غير جاهزة")

    direction = None
    reason = []

    if ema9 > ema21 and rsi14 > 52 and current_price > prev["close"]:
        direction = "BUY"
        reason.append("EMA9 فوق EMA21")
        reason.append("RSI داعم للصعود")
        reason.append("الإغلاق الأخير أعلى من السابق")
    elif ema9 < ema21 and rsi14 < 48 and current_price < prev["close"]:
        direction = "SELL"
        reason.append("EMA9 تحت EMA21")
        reason.append("RSI داعم للهبوط")
        reason.append("الإغلاق الأخير أقل من السابق")
    else:
        direction = "WAIT"
        reason.append("الشروط الفنية غير مكتملة")
        reason.append("الاتجاه غير واضح الآن")

    recent_range = last["high"] - last["low"]
    if recent_range <= 0:
        recent_range = max(current_price * 0.002, 1.0)

    stop_distance = round(recent_range * 1.2, 2)
    take_distance = round(stop_distance * 1.5, 2)

    if direction == "BUY":
        entry = round(current_price, 2)
        sl = round(entry - stop_distance, 2)
        tp = round(entry + take_distance, 2)
    elif direction == "SELL":
        entry = round(current_price, 2)
        sl = round(entry + stop_distance, 2)
        tp = round(entry - take_distance, 2)
    else:
        entry = round(current_price, 2)
        sl = None
        tp = None

    return {
        "symbol": market["symbol"],
        "currency": market["currency"],
        "price": round(current_price, 2),
        "prev_close": round(market["prev_close"], 2),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "rsi14": round(rsi14, 2),
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "reason": reason,
    }


def format_signal(sig: dict) -> str:
    if sig["direction"] == "WAIT":
        return (
            f"📊 تحليل الذهب الحقيقي\n\n"
            f"🟡 السعر الحالي: {sig['price']} {sig['currency']}\n"
            f"📈 EMA9: {sig['ema9']}\n"
            f"📉 EMA21: {sig['ema21']}\n"
            f"📍 RSI14: {sig['rsi14']}\n\n"
            f"⏳ القرار: انتظار\n"
            f"🧠 السبب:\n- " + "\n- ".join(sig["reason"]) + "\n\n"
            f"📩 التواصل: {CONTACT_USERNAME}"
        )

    arrow = "📈" if sig["direction"] == "BUY" else "📉"
    ar_text = "شراء" if sig["direction"] == "BUY" else "بيع"

    return (
        f"📊 تحليل الذهب الحقيقي\n\n"
        f"{arrow} الصفقة: {ar_text} GOLD\n"
        f"🟡 الدخول: {sig['entry']} {sig['currency']}\n"
        f"🎯 الهدف: {sig['tp']} {sig['currency']}\n"
        f"🛑 الوقف: {sig['sl']} {sig['currency']}\n\n"
        f"📈 EMA9: {sig['ema9']}\n"
        f"📉 EMA21: {sig['ema21']}\n"
        f"📍 RSI14: {sig['rsi14']}\n\n"
        f"🧠 السبب:\n- " + "\n- ".join(sig["reason"]) + "\n\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )


# =========================
# الأوامر
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rec = get_user_record(user.id)
    rec["username"] = f"@{user.username}" if user.username else ""
    rec["first_name"] = user.first_name or ""
    save_data(db)

    text = (
        f"🔥 أهلاً بك في {BOT_NAME} 🔥\n\n"
        f"✅ تحليل ذهب حقيقي مبني على EMA + RSI\n"
        f"✅ سعر ذهب حقيقي من السوق\n"
        f"✅ صفقتان يوميًا فقط\n"
        f"✅ أول صفقتين مجانًا ثم VIP\n\n"
        f"الأوامر:\n"
        f"/price - سعر الذهب الآن\n"
        f"/signal - تحليل يدوي الآن\n"
        f"/vip - معلومات الاشتراك\n"
        f"/status - وضع حسابك\n"
        f"/myid - إظهار ID\n\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID تبعك: {update.effective_user.id}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rec = get_user_record(update.effective_user.id)
    reset_daily_if_needed(rec)
    save_data(db)

    vip_text = "نعم ✅" if is_vip_active(rec) else "لا ❌"
    vip_until = rec["vip_until"] if rec["vip_until"] else "غير مفعل"

    text = (
        f"📋 حالة الحساب\n\n"
        f"🎁 المجاني المستخدم: {rec['free_total_used']} / 2\n"
        f"📨 إشارات اليوم: {rec['received_today']} / 2\n"
        f"💎 VIP: {vip_text}\n"
        f"📅 نهاية VIP: {vip_until}\n\n"
        f"📩 {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        market = fetch_gold_chart(range_value="1d", interval="5m")
        if not market or "price" not in market:
            raise ValueError("no data")

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
    rec = get_user_record(update.effective_user.id)

    if not can_receive_signal(rec):
        if rec["received_today"] >= 2:
            await update.message.reply_text(
                f"⛔ وصلت الحد اليومي: صفقتان فقط.\n\n"
                f"📩 VIP: {CONTACT_USERNAME}"
            )
            return

        if not is_vip_active(rec) and rec["free_total_used"] >= 2:
            await update.message.reply_text(
                f"⛔ انتهت أول صفقتين مجانًا.\n"
                f"💎 للاشتراك VIP: {CONTACT_USERNAME}"
            )
            return

        await update.message.reply_text("⛔ لا يمكنك استلام صفقة الآن")
        return

    try:
        sig = build_signal()
        mark_signal_sent(rec)
        save_data(db)
        await update.message.reply_text(format_signal(sig))

    except Exception as e:
        print("SIGNAL ERROR:", e)
        await update.message.reply_text("❌ فشل التحليل حالياً، حاول لاحقاً")


async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"💎 اشتراك VIP\n\n"
        f"✔ بعد انتهاء المجاني\n"
        f"✔ استمرار استقبال الصفقات\n"
        f"✔ استخدام البوت بدون توقف المجاني\n\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("استعمال الأمر:\n/addvip USER_ID DAYS")
        return

    target_user_id = context.args[0]
    days = int(context.args[1])

    rec = get_user_record(int(target_user_id))
    rec["vip_until"] = (datetime.now() + timedelta(days=days)).isoformat()
    save_data(db)

    await update.message.reply_text(
        f"✅ تم تفعيل VIP للمستخدم {target_user_id}\n"
        f"📅 لمدة {days} يوم"
    )


async def delvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 1:
        await update.message.reply_text("استعمال الأمر:\n/delvip USER_ID")
        return

    target_user_id = context.args[0]
    rec = get_user_record(int(target_user_id))
    rec["vip_until"] = None
    save_data(db)

    await update.message.reply_text(f"✅ تم حذف VIP عن {target_user_id}")


async def auto_signal(context: ContextTypes.DEFAULT_TYPE):
    try:
        sig = build_signal()
        text = format_signal(sig)
    except Exception as e:
        print("AUTO SIGNAL ERROR:", e)
        return

    sent_count = 0

    for uid, rec in db["users"].items():
        try:
            if not can_receive_signal(rec):
                continue

            await context.bot.send_message(chat_id=int(uid), text=text)
            mark_signal_sent(rec)
            sent_count += 1
        except Exception as e:
            print(f"SEND ERROR {uid}: {e}")

    save_data(db)
    print(f"Auto signal sent to {sent_count} users")


# =========================
# التشغيل
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("vip", vip))
    app.add_handler(CommandHandler("addvip", addvip))
    app.add_handler(CommandHandler("delvip", delvip))

    # إشارتان يومياً
    app.job_queue.run_daily(auto_signal, time=time(hour=13, minute=0, second=0), name="signal_1")
    app.job_queue.run_daily(auto_signal, time=time(hour=17, minute=0, second=0), name="signal_2")

    print("🔥 Bot running Abod...")
    app.run_polling()


if __name__ == "__main__":
    main()
