import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

import pandas as pd
import yfinance as yf

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# الإعدادات
# =========================================================
BOT_TOKEN = "8749740785:AAGuy3TA2jb-SQ1xt9-VJ1X0sG0A7yk17No"

OWNER_NAME = "Abod"
OWNER_USERNAME = "@Abod_gold"
OWNER_ID = 5322650589  # حط ايديك الحقيقي هون

DATA_FILE = "users_data.json"

FREE_SIGNALS_LIMIT = 2
SIGNAL_COOLDOWN_SECONDS = 15

# مصادر الذهب
GOLD_SYMBOLS = ["XAUUSD=X", "GC=F"]

# =========================================================
# اللوج
# =========================================================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================================================
# التخزين
# =========================================================
def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {"users": {}}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"خطأ بقراءة ملف البيانات: {e}")
        return {"users": {}}


def save_data(data: Dict[str, Any]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"خطأ بحفظ ملف البيانات: {e}")


db = load_data()

# =========================================================
# أدوات المستخدمين
# =========================================================
def ensure_user(user_id: int, username: Optional[str], full_name: str) -> Dict[str, Any]:
    uid = str(user_id)

    if "users" not in db:
        db["users"] = {}

    if uid not in db["users"]:
        db["users"][uid] = {
            "username": username or "",
            "full_name": full_name or "",
            "free_signals_used": 0,
            "vip_until": None,
            "last_signal_time": None,
            "joined_at": datetime.utcnow().isoformat()
        }
        save_data(db)
    else:
        db["users"][uid]["username"] = username or db["users"][uid].get("username", "")
        db["users"][uid]["full_name"] = full_name or db["users"][uid].get("full_name", "")
        save_data(db)

    return db["users"][uid]


def is_vip(user_data: Dict[str, Any]) -> bool:
    vip_until = user_data.get("vip_until")
    if not vip_until:
        return False
    try:
        return datetime.utcnow() < datetime.fromisoformat(vip_until)
    except Exception:
        return False


def can_get_signal(user_data: Dict[str, Any]) -> Tuple[bool, str]:
    if is_vip(user_data):
        return True, "VIP"

    used = int(user_data.get("free_signals_used", 0))
    if used < FREE_SIGNALS_LIMIT:
        remaining = FREE_SIGNALS_LIMIT - used
        return True, f"مجاني. المتبقي: {remaining}"
    return False, "انتهت المحاولات المجانية. راسل الدعم للاشتراك."


def check_cooldown(user_data: Dict[str, Any]) -> Tuple[bool, int]:
    last_signal_time = user_data.get("last_signal_time")
    if not last_signal_time:
        return True, 0

    try:
        last_dt = datetime.fromisoformat(last_signal_time)
        diff = (datetime.utcnow() - last_dt).total_seconds()
        if diff >= SIGNAL_COOLDOWN_SECONDS:
            return True, 0
        return False, int(SIGNAL_COOLDOWN_SECONDS - diff)
    except Exception:
        return True, 0


def mark_signal_used(user_id: int) -> None:
    uid = str(user_id)
    if uid not in db["users"]:
        return

    if not is_vip(db["users"][uid]):
        db["users"][uid]["free_signals_used"] = int(db["users"][uid].get("free_signals_used", 0)) + 1

    db["users"][uid]["last_signal_time"] = datetime.utcnow().isoformat()
    save_data(db)

# =========================================================
# جلب البيانات
# =========================================================
def fetch_gold_data(period: str = "7d", interval: str = "15m") -> pd.DataFrame:
    """
    يجلب بيانات الذهب من Yahoo Finance
    """
    last_error = None

    for symbol in GOLD_SYMBOLS:
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False
            )

            if df is not None and not df.empty:
                df = df.copy()
                df.dropna(inplace=True)

                # أحياناً ترجع الأعمدة MultiIndex
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] for col in df.columns]

                required_cols = {"Open", "High", "Low", "Close", "Volume"}
                if required_cols.issubset(set(df.columns)):
                    return df

        except Exception as e:
            last_error = e
            logger.warning(f"فشل الجلب من {symbol}: {e}")

    raise RuntimeError(f"تعذر جلب بيانات الذهب. آخر خطأ: {last_error}")

# =========================================================
# المؤشرات
# =========================================================
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    macd_line = ema12 - ema26
    signal_line = ema(macd_line, 9)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(length).mean()


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)

    atr_val = tr.rolling(length).mean().replace(0, 1e-10)
    plus_di = 100 * (plus_dm.rolling(length).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(length).mean() / atr_val)

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)) * 100
    return dx.rolling(length).mean()


def stochastic(df: pd.DataFrame, length: int = 14) -> pd.Series:
    low_min = df["Low"].rolling(length).min()
    high_max = df["High"].rolling(length).max()
    k = 100 * ((df["Close"] - low_min) / (high_max - low_min).replace(0, 1e-10))
    return k


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["EMA9"] = ema(df["Close"], 9)
    df["EMA21"] = ema(df["Close"], 21)
    df["EMA50"] = ema(df["Close"], 50)
    df["EMA200"] = ema(df["Close"], 200)

    df["RSI"] = rsi(df["Close"], 14)

    macd_line, signal_line, hist = macd(df["Close"])
    df["MACD"] = macd_line
    df["MACD_SIGNAL"] = signal_line
    df["MACD_HIST"] = hist

    df["ATR"] = atr(df, 14)
    df["ADX"] = adx(df, 14)
    df["STOCH_K"] = stochastic(df, 14)

    df["VOL_MA20"] = df["Volume"].rolling(20).mean()

    return df.dropna()

# =========================================================
# التحليل
# =========================================================
def get_support_resistance(df: pd.DataFrame, lookback: int = 20) -> Tuple[float, float]:
    recent = df.tail(lookback)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    return support, resistance


def score_to_text(score: int) -> str:
    if score >= 85:
        return "عالية جدًا"
    elif score >= 70:
        return "عالية"
    elif score >= 55:
        return "متوسطة"
    elif score >= 40:
        return "ضعيفة"
    return "ضعيفة جدًا"


def build_signal(df: pd.DataFrame) -> Dict[str, Any]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(latest["Close"])
    atr_val = float(latest["ATR"])
    support, resistance = get_support_resistance(df, lookback=20)

    buy_score = 0
    sell_score = 0
    reasons_buy = []
    reasons_sell = []

    # الاتجاه
    if latest["EMA9"] > latest["EMA21"]:
        buy_score += 12
        reasons_buy.append("EMA9 فوق EMA21")
    else:
        sell_score += 12
        reasons_sell.append("EMA9 تحت EMA21")

    if latest["EMA21"] > latest["EMA50"]:
        buy_score += 10
        reasons_buy.append("EMA21 فوق EMA50")
    else:
        sell_score += 10
        reasons_sell.append("EMA21 تحت EMA50")

    if price > latest["EMA200"]:
        buy_score += 10
        reasons_buy.append("السعر فوق EMA200")
    else:
        sell_score += 10
        reasons_sell.append("السعر تحت EMA200")

    # RSI
    if 55 <= latest["RSI"] <= 72:
        buy_score += 12
        reasons_buy.append("RSI داعم للشراء")
    elif 28 <= latest["RSI"] <= 45:
        sell_score += 12
        reasons_sell.append("RSI داعم للبيع")

    # MACD
    if latest["MACD"] > latest["MACD_SIGNAL"] and latest["MACD_HIST"] > prev["MACD_HIST"]:
        buy_score += 14
        reasons_buy.append("MACD إيجابي")
    if latest["MACD"] < latest["MACD_SIGNAL"] and latest["MACD_HIST"] < prev["MACD_HIST"]:
        sell_score += 14
        reasons_sell.append("MACD سلبي")

    # ADX
    if latest["ADX"] >= 20:
        if buy_score > sell_score:
            buy_score += 10
            reasons_buy.append("اتجاه قوي ADX")
        elif sell_score > buy_score:
            sell_score += 10
            reasons_sell.append("اتجاه قوي ADX")

    # Stochastic
    if latest["STOCH_K"] < 25 and latest["RSI"] > 45:
        buy_score += 8
        reasons_buy.append("خروج من تشبع بيع")
    elif latest["STOCH_K"] > 75 and latest["RSI"] < 55:
        sell_score += 8
        reasons_sell.append("خروج من تشبع شراء")

    # حجم تداول
    if latest["Volume"] > latest["VOL_MA20"]:
        if buy_score > sell_score:
            buy_score += 6
            reasons_buy.append("فوليوم داعم")
        elif sell_score > buy_score:
            sell_score += 6
            reasons_sell.append("فوليوم داعم")

    # قرب السعر من الدعم/المقاومة
    dist_support = abs(price - support)
    dist_resistance = abs(resistance - price)

    if dist_support < atr_val * 1.2 and latest["RSI"] > 45:
        buy_score += 8
        reasons_buy.append("قرب من دعم")
    if dist_resistance < atr_val * 1.2 and latest["RSI"] < 55:
        sell_score += 8
        reasons_sell.append("قرب من مقاومة")

    # القرار النهائي
    signal = "WAIT"
    score = max(buy_score, sell_score)
    reasons = []

    if buy_score >= 58 and buy_score > sell_score + 8:
        signal = "BUY"
        reasons = reasons_buy
    elif sell_score >= 58 and sell_score > buy_score + 8:
        signal = "SELL"
        reasons = reasons_sell

    # قوة الدخول
    entry_strength = min(100, int(score))

    # فلترة إضافية
    if atr_val <= 0:
        signal = "WAIT"

    # تحديد الدخول والوقف والأهداف
    entry = round(price, 2)

    if signal == "BUY":
        sl = round(entry - atr_val * 1.6, 2)
        tp1 = round(entry + atr_val * 1.8, 2)
        tp2 = round(entry + atr_val * 3.0, 2)
    elif signal == "SELL":
        sl = round(entry + atr_val * 1.6, 2)
        tp1 = round(entry - atr_val * 1.8, 2)
        tp2 = round(entry - atr_val * 3.0, 2)
    else:
        sl = 0.0
        tp1 = 0.0
        tp2 = 0.0

    rr = 0.0
    if signal == "BUY" and entry != sl:
        rr = round((tp1 - entry) / (entry - sl), 2)
    elif signal == "SELL" and entry != sl:
        rr = round((entry - tp1) / (sl - entry), 2)

    return {
        "signal": signal,
        "price": round(price, 2),
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rr": rr,
        "score": score,
        "score_text": score_to_text(score),
        "entry_strength": score_to_text(entry_strength),
        "buy_score": buy_score,
        "sell_score": sell_score,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "rsi": round(float(latest["RSI"]), 2),
        "adx": round(float(latest["ADX"]), 2),
        "atr": round(float(atr_val), 2),
        "reasons": reasons[:5]
    }

# =========================================================
# تنسيق الرسائل
# =========================================================
def format_signal_message(analysis: Dict[str, Any]) -> str:
    if analysis["signal"] == "WAIT":
        return (
            "⏳ لا توجد صفقة قوية الآن\n\n"
            f"💰 السعر الحالي: {analysis['price']}\n"
            f"📊 قوة الإشارة: {analysis['score_text']} ({analysis['score']}/100)\n"
            f"📍 الدعم: {analysis['support']}\n"
            f"📍 المقاومة: {analysis['resistance']}\n"
            f"📈 RSI: {analysis['rsi']}\n"
            f"📈 ADX: {analysis['adx']}\n\n"
            "السبب: السوق حالياً لا يعطي دخول نظيف وآمن."
        )

    signal_emoji = "🟢 شراء" if analysis["signal"] == "BUY" else "🔴 بيع"

    reasons_text = "\n".join([f"• {r}" for r in analysis["reasons"]]) if analysis["reasons"] else "• لا يوجد"

    return (
        f"🔥 إشارة ذهب احترافية\n\n"
        f"📌 النوع: {signal_emoji}\n"
        f"💰 السعر الحالي: {analysis['price']}\n"
        f"🎯 نقطة الدخول: {analysis['entry']}\n"
        f"🛑 وقف الخسارة: {analysis['sl']}\n"
        f"✅ الهدف 1: {analysis['tp1']}\n"
        f"✅ الهدف 2: {analysis['tp2']}\n"
        f"📊 قوة الإشارة: {analysis['score_text']} ({analysis['score']}/100)\n"
        f"🚀 قوة الدخول: {analysis['entry_strength']}\n"
        f"⚖️ نسبة العائد للمخاطرة: {analysis['rr']}\n\n"
        f"📈 RSI: {analysis['rsi']}\n"
        f"📈 ADX: {analysis['adx']}\n"
        f"📏 ATR: {analysis['atr']}\n"
        f"📍 الدعم: {analysis['support']}\n"
        f"📍 المقاومة: {analysis['resistance']}\n\n"
        f"🧠 أسباب الإشارة:\n{reasons_text}\n\n"
        f"👤 للتواصل: {OWNER_NAME} - {OWNER_USERNAME}"
    )

# =========================================================
# الكيبورد
# =========================================================
def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["/start", "/price"],
            ["/signal", "/vip"],
            ["/help"]
        ],
        resize_keyboard=True
    )

# =========================================================
# الأوامر
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username, user.full_name)

    text = (
        f"أهلاً {user.first_name or 'فيك'} 👋\n\n"
        "أنا بوت تحليل الذهب.\n"
        "أعطيك إشارات ذهب مع تحليل أقوى وفلترة أفضل.\n\n"
        f"🎁 أول {FREE_SIGNALS_LIMIT} إشارتين مجاناً\n"
        "بعدها تحتاج اشتراك VIP.\n\n"
        "الأوامر:\n"
        "/price - سعر الذهب الآن\n"
        "/signal - صفقة وتحليل\n"
        "/vip - معلومات الاشتراك\n"
        "/help - شرح الأوامر\n\n"
        f"الدعم: {OWNER_USERNAME}"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 شرح الأوامر:\n\n"
        "/start - تشغيل البوت\n"
        "/price - عرض السعر الحالي للذهب\n"
        "/signal - استخراج إشارة تداول\n"
        "/vip - الاشتراك والتواصل\n"
        "/help - المساعدة\n\n"
        "ملاحظة:\n"
        "الإشارات ليست مضمونة 100%، وإدارة رأس المال ضرورية."
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())


async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        df = fetch_gold_data(period="2d", interval="5m")
        price_now = round(float(df["Close"].iloc[-1]), 2)
        high_today = round(float(df["High"].tail(50).max()), 2)
        low_today = round(float(df["Low"].tail(50).min()), 2)

        text = (
            "📊 سعر الذهب الآن\n\n"
            f"💰 السعر الحالي: {price_now}\n"
            f"⬆️ أعلى نطاق قريب: {high_today}\n"
            f"⬇️ أدنى نطاق قريب: {low_today}\n\n"
            f"👤 الدعم: {OWNER_USERNAME}"
        )
        await update.message.reply_text(text, reply_markup=main_keyboard())

    except Exception as e:
        logger.error(f"price error: {e}")
        await update.message.reply_text(
            "❌ صار خطأ أثناء جلب سعر الذهب.\nحاول بعد قليل.",
            reply_markup=main_keyboard()
        )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_data = ensure_user(user.id, user.username, user.full_name)

        allowed, status_msg = can_get_signal(user_data)
        if not allowed:
            await update.message.reply_text(
                "🚫 انتهت الفرص المجانية.\n\n"
                f"للاشتراك تواصل مع: {OWNER_USERNAME}",
                reply_markup=main_keyboard()
            )
            return

        ready, remain = check_cooldown(user_data)
        if not ready:
            await update.message.reply_text(
                f"⏳ انتظر {remain} ثانية قبل طلب إشارة جديدة.",
                reply_markup=main_keyboard()
            )
            return

        await update.message.reply_text("⏳ جاري تحليل الذهب واستخراج أفضل إشارة...")

        df = fetch_gold_data(period="10d", interval="15m")
        df = add_indicators(df)
        analysis = build_signal(df)

        mark_signal_used(user.id)

        used = db["users"][str(user.id)].get("free_signals_used", 0)
        remaining = max(0, FREE_SIGNALS_LIMIT - used)

        footer = ""
        if not is_vip(db["users"][str(user.id)]):
            footer = f"\n\n🎁 المتبقي لك مجاناً: {remaining}"

        await update.message.reply_text(
            format_signal_message(analysis) + footer,
            reply_markup=main_keyboard()
        )

    except Exception as e:
        logger.error(f"signal error: {e}")
        await update.message.reply_text(
            "❌ فشل التحليل حالياً.\n"
            "تأكد من الإنترنت أو جرّب بعد قليل.",
            reply_markup=main_keyboard()
        )


async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = ensure_user(user.id, user.username, user.full_name)

    if is_vip(user_data):
        vip_until = user_data.get("vip_until", "")
        text = (
            "💎 أنت مشترك VIP\n\n"
            f"ينتهي الاشتراك بتاريخ:\n{vip_until}\n\n"
            f"للدعم: {OWNER_USERNAME}"
        )
    else:
        text = (
            "💎 الاشتراك VIP\n\n"
            "مميزات الاشتراك:\n"
            "• إشارات غير محدودة\n"
            "• تحليل أقوى\n"
            "• متابعة أفضل\n"
            "• أولوية بالدعم\n\n"
            f"للاشتراك راسل: {OWNER_USERNAME}"
        )

    await update.message.reply_text(text, reply_markup=main_keyboard())


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (update.message.text or "").strip().lower()

    if msg in ["اشارة", "إشارة", "signal", "صفقة", "تحليل"]:
        await signal(update, context)
        return

    if msg in ["سعر", "price", "ذهب", "gold"]:
        await price(update, context)
        return

    if msg in ["vip", "اشتراك", "اشترك"]:
        await vip(update, context)
        return

    await update.message.reply_text(
        "ما فهمت طلبك.\nاستخدم /signal أو /price أو /vip",
        reply_markup=main_keyboard()
    )

# =========================================================
# تشغيل
# =========================================================
def main():
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("حط BOT TOKEN أولاً داخل المتغير BOT_TOKEN")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("vip", vip))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
