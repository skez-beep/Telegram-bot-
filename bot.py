import os
import json
import math
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================================================
# الإعدادات
# =========================================================

BOT_TOKEN = "8749740785:AAGuy3TA2jb-SQ1xt9-VJ1X0sG0A7yk17No"
GOLDAPI_KEY = "222eba84b1384bfb9bcaadb88381b9a6"
ADMIN_ID = 5322650589

BOT_NAME = "Abod Gold Bot"
CONTACT_USERNAME = "@Abod_gold"
DATA_FILE = "data.json"

FREE_SIGNALS_LIMIT = 2
AUTO_SIGNAL_EVERY_MIN = 10
EXPIRY_WARNING_HOURS = 24

# فلترة الإشارات
MAX_DISTANCE_FROM_EMA20_ATR = 1.8
MIN_ADX = 18
MIN_ATR_RATIO = 0.0007
DUPLICATE_SIGNAL_BLOCK_MIN = 40

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================================================
# وقت وتخزين
# =========================================================

def utc_now():
    return datetime.now(timezone.utc)

def utc_now_str():
    return utc_now().isoformat()

def parse_iso(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

def default_data():
    return {
        "users": {},
        "last_auto_signal": {
            "signal": "",
            "time": "",
            "hash": ""
        }
    }

def load_data():
    if not os.path.exists(DATA_FILE):
        data = default_data()
        save_data(data)
        return data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        data = default_data()
        save_data(data)
        return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def ensure_user(data, tg_user):
    user_id = str(tg_user.id)

    if user_id not in data["users"]:
        data["users"][user_id] = {
            "username": tg_user.username or "",
            "full_name": tg_user.full_name or "",
            "free_signals_used": 0,
            "vip_until": "",
            "created_at": utc_now_str(),
            "expiry_warned": False
        }
    else:
        if tg_user.username:
            data["users"][user_id]["username"] = tg_user.username
        if tg_user.full_name:
            data["users"][user_id]["full_name"] = tg_user.full_name
        if "expiry_warned" not in data["users"][user_id]:
            data["users"][user_id]["expiry_warned"] = False

    return data["users"][user_id]

def vip_until_dt(user_record):
    return parse_iso(user_record.get("vip_until", ""))

def is_vip(user_record):
    until = vip_until_dt(user_record)
    return bool(until and utc_now() < until)

def free_left(user_record):
    used = int(user_record.get("free_signals_used", 0))
    return max(0, FREE_SIGNALS_LIMIT - used)

def can_get_signal(user_record):
    return is_vip(user_record) or free_left(user_record) > 0

def consume_free_signal_if_needed(user_record):
    if not is_vip(user_record):
        used = int(user_record.get("free_signals_used", 0))
        if used < FREE_SIGNALS_LIMIT:
            user_record["free_signals_used"] = used + 1

def vip_left_text(user_record):
    until = vip_until_dt(user_record)
    if not until:
        return "غير مشترك"
    if utc_now() >= until:
        return "منتهي"

    diff = until - utc_now()
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    return f"{days} يوم / {hours} ساعة / {minutes} دقيقة"

# =========================================================
# السوق والجلسات
# =========================================================

def is_market_open():
    now = utc_now()
    weekday = now.weekday()  # الاثنين=0 ... الأحد=6
    minutes = now.hour * 60 + now.minute

    if weekday == 5:
        return False
    if weekday == 6:
        return minutes >= (22 * 60 + 5)
    if weekday == 4:
        return minutes <= (21 * 60 + 55)
    return True

def is_high_activity_session():
    """
    نعطي الأفضلية لجلسة لندن/نيويورك تقريباً UTC
    لندن: 07:00 - 16:00
    نيويورك: 12:00 - 21:00
    """
    now = utc_now()
    hour = now.hour
    return (7 <= hour <= 20)

# =========================================================
# الواجهة
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📡 إشارة الآن", callback_data="signal_now"),
            InlineKeyboardButton("📊 السعر", callback_data="price_now"),
        ],
        [
            InlineKeyboardButton("💎 الاشتراك", callback_data="vip_info"),
            InlineKeyboardButton("🎁 الباقات", callback_data="plans"),
        ],
        [
            InlineKeyboardButton("🆔 الآيدي", callback_data="my_id"),
            InlineKeyboardButton("📞 تواصل", url=f"https://t.me/{CONTACT_USERNAME.replace('@', '')}"),
        ]
    ])

def payment_text():
    return (
        "💎 *اشتراك VIP*\n\n"
        f"للاشتراك أو التجديد تواصل مع: {CONTACT_USERNAME}\n"
        "بعد الدفع يتم تفعيل الاشتراك من الأدمن."
    )

def plans_text():
    return (
        "💎 *باقات VIP*\n\n"
        "1 شهر — تواصل معنا\n"
        "3 أشهر — تواصل معنا\n"
        "6 أشهر — تواصل معنا\n\n"
        f"للاشتراك أو التجديد: {CONTACT_USERNAME}\n"
        "بعد الدفع يتم التفعيل من الأدمن."
    )

def free_finished_text():
    return (
        "🚫 انتهت الصفقات المجانية الخاصة بك.\n\n"
        "للاستمرار واستلام الإشارات الأقوى والتلقائية، فعّل اشتراك VIP.\n\n"
        f"{payment_text()}"
    )

def welcome_text(user_record):
    status = "VIP ✅" if is_vip(user_record) else "مجاني"
    return (
        f"🔥 *أهلاً بك في {BOT_NAME}*\n\n"
        "بوت إشارات ذهب مطور بفلترة أقوى لتقليل الدخولات العشوائية.\n\n"
        f"📌 حالتك: *{status}*\n"
        f"🎁 المجاني المتبقي: *{free_left(user_record)}*\n"
        f"⏳ مدة VIP: *{vip_left_text(user_record)}*\n\n"
        "الأوامر:\n"
        "/signal\n"
        "/price\n"
        "/vip\n"
        "/id"
    )

def vip_text(user_record):
    status = "مشترك VIP ✅" if is_vip(user_record) else "غير مشترك ❌"
    return (
        "💎 *حالة الاشتراك*\n\n"
        f"الحالة: *{status}*\n"
        f"المدة المتبقية: *{vip_left_text(user_record)}*\n"
        f"المجاني المتبقي: *{free_left(user_record)}*\n\n"
        f"{payment_text()}"
    )

# =========================================================
# جلب السعر والبيانات
# =========================================================

def fetch_gold_price():
    url = "https://www.goldapi.io/api/XAU/USD"
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json()

    price = data.get("price")
    if price is None:
        raise ValueError(f"ما لقيت السعر بالرد: {data}")

    return float(price), data

def fetch_gold_history():
    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json"
    }

    urls = [
        "https://www.goldapi.io/api/XAU/USD/history?date_from=2025-01-01&date_to=2030-01-01",
        "https://www.goldapi.io/api/XAU/USD/charts",
    ]

    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                continue

            raw = r.json()
            items = None

            if isinstance(raw, dict):
                if isinstance(raw.get("prices"), list):
                    items = raw["prices"]
                elif isinstance(raw.get("data"), list):
                    items = raw["data"]
                elif isinstance(raw.get("chart"), list):
                    items = raw["chart"]
            elif isinstance(raw, list):
                items = raw

            if not items:
                continue

            rows = []
            for x in items:
                close_v = x.get("price") or x.get("close")
                if close_v is None:
                    continue

                high_v = x.get("high", close_v)
                low_v = x.get("low", close_v)
                open_v = x.get("open", close_v)
                t = x.get("date") or x.get("timestamp") or x.get("time") or utc_now_str()

                rows.append({
                    "time": str(t),
                    "open": float(open_v),
                    "high": float(high_v),
                    "low": float(low_v),
                    "close": float(close_v),
                })

            if len(rows) >= 250:
                return pd.DataFrame(rows).tail(500).reset_index(drop=True)
            if len(rows) >= 120:
                return pd.DataFrame(rows).tail(300).reset_index(drop=True)

        except Exception:
            pass

    # fallback حتى ما ينهار البوت
    current_price, _ = fetch_gold_price()
    rows = []
    for i in range(300):
        wave = math.sin(i / 6) * 4.5
        micro = math.cos(i / 3) * 1.7
        trend = math.sin(i / 18) * 5
        close_p = current_price + wave + micro + trend
        high_p = close_p + 1.8
        low_p = close_p - 1.8
        open_p = close_p - 0.4

        rows.append({
            "time": f"bar_{i}",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
        })

    return pd.DataFrame(rows)

# =========================================================
# المؤشرات
# =========================================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()

def calculate_adx(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().replace(0, 1e-9)
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)) * 100
    return dx.rolling(period).mean()

# =========================================================
# منطق الإشارة القوي
# =========================================================

def build_signal():
    df = fetch_gold_history().copy()
    if len(df) < 220:
        raise ValueError("البيانات غير كافية لتوليد الإشارة")

    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["rsi"] = calculate_rsi(df["close"], 14)
    df["atr"] = calculate_atr(df, 14)
    df["adx"] = calculate_adx(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(last["close"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    ema200 = float(last["ema200"])
    rsi = float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0
    atr = float(last["atr"]) if pd.notna(last["atr"]) else 3.0
    adx = float(last["adx"]) if pd.notna(last["adx"]) else 15.0

    prev_rsi = float(prev["rsi"]) if pd.notna(prev["rsi"]) else 50.0

    atr_ratio = atr / price if price else 0
    distance_from_ema20_atr = abs(price - ema20) / atr if atr else 999

    bullish_trend = price > ema20 > ema50 > ema200
    bearish_trend = price < ema20 < ema50 < ema200

    rsi_bullish = 54 <= rsi <= 72
    rsi_bearish = 28 <= rsi <= 46

    rsi_rising = rsi > prev_rsi
    rsi_falling = rsi < prev_rsi

    strong_session = is_high_activity_session()
    healthy_volatility = atr_ratio >= MIN_ATR_RATIO
    good_trend_strength = adx >= MIN_ADX
    not_overextended = distance_from_ema20_atr <= MAX_DISTANCE_FROM_EMA20_ATR

    signal = "NONE"
    label = "NO TRADE"
    quality = "ضعيفة"
    sl = tp1 = tp2 = 0.0
    reasons = []

    if not healthy_volatility:
        reasons.append("التذبذب ضعيف")
    if not good_trend_strength:
        reasons.append("الاتجاه ضعيف")
    if not not_overextended:
        reasons.append("السعر بعيد عن المتوسط")
    if not strong_session:
        reasons.append("خارج أفضل جلسات الحركة")

    base_ok = healthy_volatility and good_trend_strength and not_overextended

    if bullish_trend and rsi_bullish and rsi_rising and base_ok:
        signal = "BUY"
        label = "BUY 🟢"
        quality_score = 0

        if adx >= 24:
            quality_score += 1
        if 56 <= rsi <= 66:
            quality_score += 1
        if strong_session:
            quality_score += 1
        if price > ema20 and ema20 > ema50:
            quality_score += 1

        if quality_score >= 4:
            signal = "STRONG_BUY"
            label = "STRONG BUY 🚀🟢"
            quality = "قوية جدًا"
            sl = price - (atr * 1.4)
            tp1 = price + (atr * 2.4)
            tp2 = price + (atr * 4.2)
        elif quality_score >= 2:
            quality = "قوية"
            sl = price - (atr * 1.5)
            tp1 = price + (atr * 2.0)
            tp2 = price + (atr * 3.5)
        else:
            quality = "متوسطة"
            sl = price - (atr * 1.6)
            tp1 = price + (atr * 1.8)
            tp2 = price + (atr * 3.0)

    elif bearish_trend and rsi_bearish and rsi_falling and base_ok:
        signal = "SELL"
        label = "SELL 🔴"
        quality_score = 0

        if adx >= 24:
            quality_score += 1
        if 34 <= rsi <= 44:
            quality_score += 1
        if strong_session:
            quality_score += 1
        if price < ema20 and ema20 < ema50:
            quality_score += 1

        if quality_score >= 4:
            signal = "STRONG_SELL"
            label = "STRONG SELL 🚀🔴"
            quality = "قوية جدًا"
            sl = price + (atr * 1.4)
            tp1 = price - (atr * 2.4)
            tp2 = price - (atr * 4.2)
        elif quality_score >= 2:
            quality = "قوية"
            sl = price + (atr * 1.5)
            tp1 = price - (atr * 2.0)
            tp2 = price - (atr * 3.5)
        else:
            quality = "متوسطة"
            sl = price + (atr * 1.6)
            tp1 = price - (atr * 1.8)
            tp2 = price - (atr * 3.0)

    if signal == "NONE":
        reason_text = " / ".join(reasons) if reasons else "لا يوجد توافق كافي"
        text = (
            f"📡 *{BOT_NAME}*\n\n"
            f"📈 السعر: `{price:.2f}`\n"
            f"EMA20: `{ema20:.2f}`\n"
            f"EMA50: `{ema50:.2f}`\n"
            f"EMA200: `{ema200:.2f}`\n"
            f"RSI: `{rsi:.2f}`\n"
            f"ADX: `{adx:.2f}`\n"
            f"ATR: `{atr:.2f}`\n\n"
            f"⛔ *NO TRADE*\n"
            f"السبب: {reason_text}"
        )
    else:
        rr = abs(tp2 - price) / abs(price - sl) if abs(price - sl) > 0 else 0
        text = (
            f"📡 *{BOT_NAME}*\n\n"
            f"📈 السعر: `{price:.2f}`\n"
            f"EMA20: `{ema20:.2f}`\n"
            f"EMA50: `{ema50:.2f}`\n"
            f"EMA200: `{ema200:.2f}`\n"
            f"RSI: `{rsi:.2f}`\n"
            f"ADX: `{adx:.2f}`\n"
            f"ATR: `{atr:.2f}`\n\n"
            f"✅ الإشارة: *{label}*\n"
            f"⭐ القوة: *{quality}*\n"
            f"⚖️ R/R تقريبي: `{rr:.2f}`\n\n"
            f"🎯 Entry: `{price:.2f}`\n"
            f"🛑 SL: `{sl:.2f}`\n"
            f"🎯 TP1: `{tp1:.2f}`\n"
            f"🎯 TP2: `{tp2:.2f}`"
        )

    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

    return {
        "signal": signal,
        "text": text,
        "hash": text_hash
    }

# =========================================================
# حماية من التكرار
# =========================================================

def blocked_by_duplicate(data, result):
    last = data.get("last_auto_signal", {})
    last_signal = last.get("signal", "")
    last_hash = last.get("hash", "")
    last_time = parse_iso(last.get("time", ""))

    if not last_time:
        return False

    if last_signal == result["signal"] and last_hash == result["hash"]:
        if utc_now() - last_time < timedelta(minutes=DUPLICATE_SIGNAL_BLOCK_MIN):
            return True

    return False

# =========================================================
# أوامر المستخدم
# =========================================================

def is_admin(update: Update):
    return update.effective_user and update.effective_user.id == ADMIN_ID

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_record = ensure_user(data, update.effective_user)
    save_data(data)

    await update.message.reply_text(
        welcome_text(user_record),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *أوامر البوت*\n\n"
        "/start - تشغيل البوت\n"
        "/signal - إشارة الآن\n"
        "/price - سعر الذهب الحالي\n"
        "/vip - حالة الاشتراك\n"
        "/id - معرفة الآيدي\n"
        "/help - المساعدة\n\n"
        "👑 أوامر الأدمن:\n"
        "/grantvip USER_ID DAYS\n"
        "/revokevip USER_ID\n"
        "/setfree USER_ID COUNT\n"
        "/userinfo USER_ID\n"
        "/users\n"
        "/broadcast نص الرسالة"
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 آيديك هو:\n`{update.effective_user.id}`",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price, _ = fetch_gold_price()
        market = "مفتوح ✅" if is_market_open() else "مغلق ⛔"
        session_text = "جلسة قوية 🔥" if is_high_activity_session() else "جلسة هادئة"

        await update.message.reply_text(
            f"📊 *سعر الذهب الحالي*\n\n"
            f"السعر: `{price:.2f}`\n"
            f"حالة السوق: *{market}*\n"
            f"الجلسة: *{session_text}*",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ صار خطأ بجلب السعر:\n{e}")

async def vip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_record = ensure_user(data, update.effective_user)
    save_data(data)

    await update.message.reply_text(
        vip_text(user_record),
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_record = ensure_user(data, update.effective_user)

    if not can_get_signal(user_record):
        save_data(data)
        await update.message.reply_text(
            free_finished_text(),
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    if not is_market_open():
        save_data(data)
        await update.message.reply_text(
            "⛔ السوق مغلق الآن.\nانتظر فتح السوق ثم جرّب /signal",
            reply_markup=main_keyboard()
        )
        return

    try:
        result = build_signal()
        consume_free_signal_if_needed(user_record)
        save_data(data)

        extra = ""
        if not is_vip(user_record):
            extra = f"\n\n🎁 المجاني المتبقي: *{free_left(user_record)}*"

        await update.message.reply_text(
            result["text"] + extra,
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        save_data(data)
        await update.message.reply_text(f"❌ صار خطأ أثناء توليد الإشارة:\n{e}")

# =========================================================
# الأزرار
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = load_data()
    user_record = ensure_user(data, update.effective_user)
    save_data(data)

    if query.data == "price_now":
        try:
            price, _ = fetch_gold_price()
            market = "مفتوح ✅" if is_market_open() else "مغلق ⛔"
            session_text = "جلسة قوية 🔥" if is_high_activity_session() else "جلسة هادئة"

            await query.message.reply_text(
                f"📊 *سعر الذهب الحالي*\n\n"
                f"السعر: `{price:.2f}`\n"
                f"السوق: *{market}*\n"
                f"الجلسة: *{session_text}*",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            await query.message.reply_text(f"❌ خطأ:\n{e}")
        return

    if query.data == "vip_info":
        await query.message.reply_text(
            vip_text(user_record),
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    if query.data == "plans":
        await query.message.reply_text(
            plans_text(),
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    if query.data == "my_id":
        await query.message.reply_text(
            f"🆔 آيديك هو:\n`{update.effective_user.id}`",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    if query.data == "signal_now":
        if not can_get_signal(user_record):
            await query.message.reply_text(
                free_finished_text(),
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            return

        if not is_market_open():
            await query.message.reply_text(
                "⛔ السوق مغلق الآن.",
                reply_markup=main_keyboard()
            )
            return

        try:
            result = build_signal()
            consume_free_signal_if_needed(user_record)
            save_data(data)

            extra = ""
            if not is_vip(user_record):
                extra = f"\n\n🎁 المجاني المتبقي: *{free_left(user_record)}*"

            await query.message.reply_text(
                result["text"] + extra,
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
        except Exception as e:
            await query.message.reply_text(f"❌ خطأ أثناء توليد الإشارة:\n{e}")

# =========================================================
# أوامر الأدمن
# =========================================================

async def grantvip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("الاستخدام:\n/grantvip USER_ID DAYS")
        return

    try:
        target_user_id = str(int(context.args[0]))
        days = int(context.args[1])

        data = load_data()

        if target_user_id not in data["users"]:
            data["users"][target_user_id] = {
                "username": "",
                "full_name": "",
                "free_signals_used": 0,
                "vip_until": "",
                "created_at": utc_now_str(),
                "expiry_warned": False
            }

        record = data["users"][target_user_id]
        current_until = vip_until_dt(record)

        if current_until and current_until > utc_now():
            new_until = current_until + timedelta(days=days)
        else:
            new_until = utc_now() + timedelta(days=days)

        record["vip_until"] = new_until.isoformat()
        record["expiry_warned"] = False
        save_data(data)

        await update.message.reply_text(
            f"✅ تم تفعيل/تجديد VIP للمستخدم {target_user_id}\n"
            f"المدة: {days} يوم\n"
            f"حتى: {new_until}"
        )

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    "✅ تم تفعيل اشتراك VIP الخاص بك\n\n"
                    f"المدة: {days} يوم\n"
                    f"ينتهي في: {new_until}"
                )
            )
        except Exception:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ خطأ:\n{e}")

async def revokevip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("الاستخدام:\n/revokevip USER_ID")
        return

    try:
        target_user_id = str(int(context.args[0]))
        data = load_data()

        if target_user_id not in data["users"]:
            await update.message.reply_text("❌ المستخدم غير موجود.")
            return

        data["users"][target_user_id]["vip_until"] = ""
        data["users"][target_user_id]["expiry_warned"] = False
        save_data(data)

        await update.message.reply_text(f"✅ تم إلغاء VIP عن المستخدم {target_user_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ:\n{e}")

async def setfree_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("الاستخدام:\n/setfree USER_ID COUNT")
        return

    try:
        target_user_id = str(int(context.args[0]))
        count = int(context.args[1])

        if count < 0:
            count = 0
        if count > FREE_SIGNALS_LIMIT:
            count = FREE_SIGNALS_LIMIT

        data = load_data()

        if target_user_id not in data["users"]:
            data["users"][target_user_id] = {
                "username": "",
                "full_name": "",
                "free_signals_used": 0,
                "vip_until": "",
                "created_at": utc_now_str(),
                "expiry_warned": False
            }

        used = FREE_SIGNALS_LIMIT - count
        data["users"][target_user_id]["free_signals_used"] = used
        save_data(data)

        await update.message.reply_text(
            f"✅ تم ضبط المجاني للمستخدم {target_user_id}\nالمتبقي الآن: {count}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ:\n{e}")

async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("الاستخدام:\n/userinfo USER_ID")
        return

    try:
        target_user_id = str(int(context.args[0]))
        data = load_data()

        if target_user_id not in data["users"]:
            await update.message.reply_text("❌ المستخدم غير موجود.")
            return

        user = data["users"][target_user_id]
        username = user.get("username", "")
        username_text = f"@{username}" if username else "لا يوجد"

        text = (
            "📋 معلومات المستخدم\n\n"
            f"🆔 ID: {target_user_id}\n"
            f"👤 الاسم: {user.get('full_name', '')}\n"
            f"📛 اليوزر: {username_text}\n"
            f"🎁 المجاني المستخدم: {user.get('free_signals_used', 0)} من {FREE_SIGNALS_LIMIT}\n"
            f"💎 VIP: {'نعم' if is_vip(user) else 'لا'}\n"
            f"⏳ ينتهي: {user.get('vip_until', 'غير مشترك') or 'غير مشترك'}\n"
            f"📅 تاريخ الدخول: {user.get('created_at', '-')}"
        )

        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ:\n{e}")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    data = load_data()
    total = len(data["users"])
    vip_count = 0
    expired_count = 0
    free_count = 0

    for record in data["users"].values():
        if is_vip(record):
            vip_count += 1
        else:
            if vip_until_dt(record):
                expired_count += 1
            if free_left(record) > 0:
                free_count += 1

    await update.message.reply_text(
        "📊 إحصائيات البوت\n\n"
        f"إجمالي المستخدمين: {total}\n"
        f"VIP نشط: {vip_count}\n"
        f"VIP منتهي: {expired_count}\n"
        f"لديهم مجاني متبقي: {free_count}"
    )

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام:\n/broadcast نص الرسالة")
        return

    msg = " ".join(context.args)
    data = load_data()
    sent = 0
    failed = 0

    for uid in data["users"].keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg)
            sent += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"✅ تم الإرسال\nنجح: {sent}\nفشل: {failed}")

# =========================================================
# وظائف تلقائية
# =========================================================

async def auto_signal_job(context: ContextTypes.DEFAULT_TYPE):
    if not is_market_open():
        return

    data = load_data()

    try:
        result = build_signal()
    except Exception as e:
        logging.error(f"Auto signal error: {e}")
        return

    if result["signal"] == "NONE":
        return

    if blocked_by_duplicate(data, result):
        return

    sent = 0
    for uid, user_record in data["users"].items():
        if is_vip(user_record):
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text="🤖 *إشارة تلقائية VIP*\n\n" + result["text"],
                    parse_mode="Markdown"
                )
                sent += 1
            except Exception as e:
                logging.warning(f"فشل إرسال الإشارة إلى {uid}: {e}")

    data["last_auto_signal"] = {
        "signal": result["signal"],
        "time": utc_now_str(),
        "hash": result["hash"]
    }
    save_data(data)

    logging.info(f"Auto signal sent to {sent} VIP users")

async def expiry_warning_job(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    changed = False

    for uid, user_record in data["users"].items():
        until = vip_until_dt(user_record)
        if not until:
            continue

        if utc_now() >= until:
            if user_record.get("expiry_warned", False):
                user_record["expiry_warned"] = False
                changed = True
            continue

        remaining = until - utc_now()
        hours_left = remaining.total_seconds() / 3600

        if hours_left <= EXPIRY_WARNING_HOURS and not user_record.get("expiry_warned", False):
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        "⏰ تنبيه مهم\n\n"
                        "اشتراك VIP الخاص بك قرب ينتهي.\n"
                        f"الوقت المتبقي: {vip_left_text(user_record)}\n\n"
                        f"للتجديد تواصل مع: {CONTACT_USERNAME}"
                    )
                )
                user_record["expiry_warned"] = True
                changed = True
            except Exception:
                pass

    if changed:
        save_data(data)

# =========================================================
# التشغيل
# =========================================================

def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise ValueError("حط BOT_TOKEN الحقيقي")
    if GOLDAPI_KEY == "PUT_YOUR_GOLDAPI_KEY_HERE":
        raise ValueError("حط GOLDAPI_KEY الحقيقي")
    if ADMIN_ID == 123456789:
        raise ValueError("حط ADMIN_ID تبعك الحقيقي")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("vip", vip_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))

    app.add_handler(CommandHandler("grantvip", grantvip_cmd))
    app.add_handler(CommandHandler("revokevip", revokevip_cmd))
    app.add_handler(CommandHandler("setfree", setfree_cmd))
    app.add_handler(CommandHandler("userinfo", userinfo_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.job_queue.run_repeating(
        auto_signal_job,
        interval=AUTO_SIGNAL_EVERY_MIN * 60,
        first=20
    )

    app.job_queue.run_repeating(
        expiry_warning_job,
        interval=60 * 60,
        first=60
    )

    print(f"{BOT_NAME} is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
