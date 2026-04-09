import json
import os
from datetime import datetime, timedelta, time

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# الإعدادات
# =========================
TOKEN = "8749740785:AAEAg9F4GxOAAAdkDfTWdpH2u3F-leRxw8Q"
API_KEY = "222eba84b1384bfb9bcaadb88381b9a6"

ADMIN_ID = 5322650589
VIP_USERS = [5322650589]  # حسابك بدون حد
CONTACT_USERNAME = "@Abod_gold"
BOT_NAME = "Gold⚜️ TRADING"

DATA_FILE = "data.json"

# Twelve Data
TD_PRICE_URL = "https://api.twelvedata.com/price"
TD_SERIES_URL = "https://api.twelvedata.com/time_series"
TD_SYMBOL = "XAU/USD"

# إشارتان يومياً
AUTO_SIGNAL_TIMES = [
    time(hour=13, minute=0, second=0),
    time(hour=17, minute=0, second=0),
]

# =========================
# التخزين
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
# جلب السعر والبيانات
# =========================
def get_gold_price():
    params = {
        "symbol": TD_SYMBOL,
        "apikey": API_KEY,
    }

    last_error = None

    for _ in range(3):
        try:
            response = requests.get(TD_PRICE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if "price" not in data:
                raise ValueError(data.get("message", "Price not found"))

            return float(data["price"])
        except Exception as e:
            last_error = e

    print("PRICE ERROR:", last_error)
    return None


def fetch_gold_chart(interval="15min", outputsize=120):
    params = {
        "symbol": TD_SYMBOL,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": API_KEY,
        "format": "JSON",
    }

    last_error = None

    for _ in range(3):
        try:
            response = requests.get(TD_SERIES_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "error":
                raise ValueError(data.get("message", "API error"))

            values = data.get("values")
            if not values or len(values) < 50:
                raise ValueError("البيانات قليلة")

            values = list(reversed(values))

            candles = []
            for row in values:
                o = row.get("open")
                h = row.get("high")
                l = row.get("low")
                c = row.get("close")
                dt = row.get("datetime")

                if None in (o, h, l, c, dt):
                    continue

                candles.append(
                    {
                        "time": dt,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                    }
                )

            if len(candles) < 50:
                raise ValueError("البيانات بعد التنظيف قليلة")

            return {
                "price": candles[-1]["close"],
                "prev_close": candles[-2]["close"],
                "currency": "USD",
                "symbol": TD_SYMBOL,
                "candles": candles,
            }

        except Exception as e:
            last_error = e

    raise ValueError(f"فشل جلب بيانات الذهب: {last_error}")


# =========================
# المؤشرات
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
            abs(low - prev_close),
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
            abs(curr["low"] - prev["close"]),
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

    return adx_valuedef build_signal():
    market = fetch_gold_chart(interval="1m")
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

    # ================== الإشارة ==================
    signal = "NONE"
    entry = round(current_price, 2)
    sl = None
    tp1 = None
    tp2 = None

    if ema9 > ema21 and rsi14 > 55 and adx14 > 25:
        signal = "BUY 🟢 (سكالب)"
        sl = round(entry - (atr14 * 1.5), 2)
        tp1 = round(entry + (atr14 * 1.5), 2)
        tp2 = round(entry + (atr14 * 2), 2)

    elif ema9 < ema21 and rsi14 < 45 and adx14 > 25:
        signal = "SELL 🔴 (سكالب)"
        sl = round(entry + (atr14 * 1.5), 2)
        tp1 = round(entry - (atr14 * 1.5), 2)
        tp2 = round(entry - (atr14 * 2), 2)

    return {
        "symbol": market["symbol"],
        "currency": market["currency"],
        "price": round(current_price, 2),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "rsi14": round(rsi14, 2),
        "atr14": round(atr14, 2),
        "adx14": round(adx14, 2),
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2
    }
        def build_signal():
    market = fetch_gold_chart(interval="1m")
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

    # ================== الإشارة ==================
    signal = "NONE"
    entry = round(current_price, 2)
    sl = None
    tp1 = None
    tp2 = None

    if ema9 > ema21 and rsi14 > 55 and adx14 > 25:
        signal = "BUY 🟢 (سكالب)"
        sl = round(entry - (atr14 * 1.5), 2)
        tp1 = round(entry + (atr14 * 1.5), 2)
        tp2 = round(entry + (atr14 * 2), 2)

    elif ema9 < ema21 and rsi14 < 45 and adx14 > 25:
        signal = "SELL 🔴 (سكالب)"
        sl = round(entry + (atr14 * 1.5), 2)
        tp1 = round(entry - (atr14 * 1.5), 2)
        tp2 = round(entry - (atr14 * 2), 2)

    return {
        "symbol": market["symbol"],
        "currency": market["currency"],
        "price": round(current_price, 2),
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "rsi14": round(rsi14, 2),
        "atr14": round(atr14, 2),
        "adx14": round(adx14, 2),
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2
    }


def format_signal(sig):
    if sig["signal"] == "NONE":
        return (
            f"📊 تحليل الذهب\n\n"
            f"🟡 السعر: USD {sig['price']}\n\n"
            f"📈 EMA9: {sig['ema9']}\n"
            f"📉 EMA21: {sig['ema21']}\n"
            f"📍 RSI14: {sig['rsi14']}\n"
            f"💪 ADX14: {sig['adx14']}\n"
            f"🔪 ATR14: {sig['atr14']}\n\n"
            f"⏳ لا توجد صفقة حالياً\n"
            f"🤖 البوت يتجنب الدخول العشوائي\n\n"
            f"✉️ @{CONTACT_USERNAME}"
        )
    else:
        return (
            f"🔥 صفقة سكالب جديدة!\n\n"
            f"🟡 السعر: USD {sig['price']}\n\n"
            f"📈 EMA9: {sig['ema9']}\n"
            f"📉 EMA21: {sig['ema21']}\n"
            f"📍 RSI14: {sig['rsi14']}\n"
            f"💪 ADX14: {sig['adx14']}\n"
            f"🔪 ATR14: {sig['atr14']}\n\n"
            f"📢 النوع: {sig['signal']}\n"
            f"🎯 Entry: {sig['entry']}\n"
            f"🛑 SL: {sig['sl']}\n"
            f"💰 TP1: {sig['tp1']}\n"
            f"💰 TP2: {sig['tp2']}\n\n"
            f"⚡ صفقة سريعة (سكالب)\n"
            f"✉️ @{CONTACT_USERNAME}"
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
        f"✅ سعر XAU/USD حقيقي\n"
        f"✅ تحليل أقوى\n"
        f"✅ صفقتان يومياً\n"
        f"✅ أول صفقتين مجاناً ثم VIP شهري\n\n"
        f"الأوامر:\n"
        f"/price - سعر الذهب الآن\n"
        f"/signal - تحليل يدوي الآن\n"
        f"/status - وضع حسابك\n"
        f"/vip - معلومات الاشتراك\n"
        f"/myid - إظهار ID\n\n"
        f"📩 التواصل: {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 ID تبعك: {update.effective_user.id}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rec = get_user_record(user_id)
    reset_daily_if_needed(rec)
    save_data(db)

    vip_text = "نعم ✅" if is_vip_active(user_id, rec) else "لا ❌"
    vip_until = "دائم ♾️" if is_unlimited_user(user_id) else (rec["vip_until"] or "غير مفعل")

    text = (
        f"📋 حالة الحساب\n\n"
        f"🎁 المجاني المستخدم: {rec['free_total_used']} / 2\n"
        f"📨 إشارات اليوم: {rec['received_today']} / 2\n"
        f"💎 VIP: {vip_text}\n"
        f"📅 نهاية الاشتراك: {vip_until}\n\n"
        f"📩 {CONTACT_USERNAME}"
    )
    await update.message.reply_text(text)


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sig = build_signal()

        await update.message.reply_text(
            f"📊 سعر الذهب الآن\n\n"
            f"🟡 السعر: {sig['price']} USD\n"
            f"📩 {CONTACT_USERNAME}"
        )

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
    await update.message.reply_text(
        f"💎 اشتراك VIP الشهري\n\n"
        f"مدة الاشتراك: 30 يوم\n"
        f"للتفعيل تواصل معي:\n{CONTACT_USERNAME}"
    )


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


# =========================
# الإرسال التلقائي
# =========================
async def auto_signal(context: ContextTypes.DEFAULT_TYPE):
    try:
        sig = build_signal()
    except Exception as e:
        print("AUTO SIGNAL ERROR:", e)
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

    for i, signal_time in enumerate(AUTO_SIGNAL_TIMES, start=1):
        app.job_queue.run_daily(auto_signal, time=signal_time, name=f"auto_signal_{i}")

    print("🔥 Bot running Abod...")
    app.run_polling()


if __name__ == "__main__":
    main()
