import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional

import pandas as pd
import yfinance as yf

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# =========================================================
# الإعدادات
# =========================================================
BOT_TOKEN = "8749740785:AAGuy3TA2jb-SQ1xt9-VJ1X0sG0A7yk17No"

OWNER_NAME = "Abod"
OWNER_USERNAME = "Abod_gold"
OWNER_ID = 5322650589  # حط ايديك الحقيقي

DATA_FILE = "users_data.json"
FREE_SIGNALS_LIMIT = 2
SIGNAL_COOLDOWN_SECONDS = 20

# كل كم دقيقة ترسل إشارة تلقائية للمشتركين
AUTO_SIGNAL_INTERVAL_MINUTES = 30

# مصادر سعر الذهب
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
def default_db() -> Dict[str, Any]:
    return {
        "users": {},
        "stats": {
            "total_signals_sent_manual": 0,
            "total_signals_sent_auto": 0,
            "buy_count": 0,
            "sell_count": 0,
            "wait_count": 0,
        }
    }

def load_db() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return default_db()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "users" not in data:
                data["users"] = {}
            if "stats" not in data:
                data["stats"] = default_db()["stats"]
            return data
    except Exception as e:
        logger.error(f"load_db error: {e}")
        return default_db()

def save_db(db: Dict[str, Any]) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"save_db error: {e}")

DB = load_db()

def get_user_record(user_id: int) -> Dict[str, Any]:
    uid = str(user_id)
    if uid not in DB["users"]:
        DB["users"][uid] = {
            "free_signals_used": 0,
            "vip_until": None,
            "last_signal_time": 0,
            "auto_signals": False,
            "joined_at": datetime.now().isoformat(),
        }
        save_db(DB)
    return DB["users"][uid]

def is_vip(record: Dict[str, Any]) -> bool:
    vip_until = record.get("vip_until")
    if not vip_until:
        return False
    try:
        return datetime.fromisoformat(vip_until) > datetime.now()
    except Exception:
        return False

def free_left(record: Dict[str, Any]) -> int:
    used = int(record.get("free_signals_used", 0))
    return max(0, FREE_SIGNALS_LIMIT - used)

def count_total_users() -> int:
    return len(DB["users"])

def count_vip_users() -> int:
    total = 0
    for rec in DB["users"].values():
        if is_vip(rec):
            total += 1
    return total

def count_auto_users() -> int:
    total = 0
    for rec in DB["users"].values():
        if is_vip(rec) and rec.get("auto_signals", False):
            total += 1
    return total

# =========================================================
# الواجهة
# =========================================================
def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["📡 إشارة الآن", "📊 السعر"],
            ["💎 الاشتراك", "🎁 الباقات"],
            ["🤖 التلقائي", "🆔 الأيدي"],
            ["📈 الإحصائيات", "📞 تواصل"],
        ],
        resize_keyboard=True
    )

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 تواصل مع الدعم", url=f"https://t.me/{OWNER_USERNAME}")]
    ])

# =========================================================
# المؤشرات
# =========================================================
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# =========================================================
# بيانات السوق
# =========================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df

def fetch_gold_dataframe(interval: str = "15m", period: str = "5d") -> Tuple[pd.DataFrame, str]:
    last_error = None

    for symbol in GOLD_SYMBOLS:
        try:
            df = yf.download(
                tickers=symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            if df is None or df.empty:
                continue

            df = normalize_columns(df)
            df = df.dropna().copy()

            required = {"Open", "High", "Low", "Close"}
            if not required.issubset(set(df.columns)):
                continue

            if len(df) < 60:
                continue

            return df, symbol

        except Exception as e:
            last_error = e
            logger.error(f"fetch_gold_dataframe failed for {symbol}: {e}")

    raise Exception(f"تعذر جلب بيانات الذهب. {last_error if last_error else ''}")

def get_current_price() -> Tuple[float, str]:
    df, symbol = fetch_gold_dataframe(interval="5m", period="1d")
    return float(df["Close"].iloc[-1]), symbol

# =========================================================
# منطق الإشارة
# =========================================================
def build_signal() -> Dict[str, Any]:
    df, symbol = fetch_gold_dataframe(interval="15m", period="5d")

    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"], 14)
    df["ATR"] = calculate_atr(df, 14)

    df = df.dropna().copy()

    if len(df) < 60:
        raise Exception("البيانات غير كافية لتوليد الإشارة")

    row = df.iloc[-1]
    prev = df.iloc[-2]

    price = float(row["Close"])
    ema9 = float(row["EMA9"])
    ema21 = float(row["EMA21"])
    ema50 = float(row["EMA50"])
    rsi = float(row["RSI"])
    atr = float(row["ATR"])

    trend_up = ema9 > ema21 > ema50
    trend_down = ema9 < ema21 < ema50

    cross_up = prev["EMA9"] <= prev["EMA21"] and row["EMA9"] > row["EMA21"]
    cross_down = prev["EMA9"] >= prev["EMA21"] and row["EMA9"] < row["EMA21"]

    momentum_buy = 55 <= rsi <= 72
    momentum_sell = 28 <= rsi <= 45

    signal = "WAIT 🟡"
    reason = "لا يوجد توافق كافي بين الاتجاه والزخم."
    sl = None
    tp1 = None
    tp2 = None
    score = 45

    if (trend_up and momentum_buy) or (cross_up and rsi >= 52):
        signal = "BUY 🟢"
        sl = round(price - (atr * 1.4), 2)
        tp1 = round(price + (atr * 1.6), 2)
        tp2 = round(price + (atr * 2.5), 2)
        reason = "اتجاه صاعد مع دعم من RSI."
        score = 78 if trend_up else 71

    elif (trend_down and momentum_sell) or (cross_down and rsi <= 48):
        signal = "SELL 🔴"
        sl = round(price + (atr * 1.4), 2)
        tp1 = round(price - (atr * 1.6), 2)
        tp2 = round(price - (atr * 2.5), 2)
        reason = "اتجاه هابط مع دعم من RSI."
        score = 78 if trend_down else 71

    return {
        "symbol": symbol,
        "signal": signal,
        "entry": round(price, 2),
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "ema9": round(ema9, 2),
        "ema21": round(ema21, 2),
        "ema50": round(ema50, 2),
        "rsi": round(rsi, 2),
        "atr": round(atr, 2),
        "score": score,
        "reason": reason,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def update_signal_stats(sig: Dict[str, Any], auto: bool = False) -> None:
    if sig["signal"].startswith("BUY"):
        DB["stats"]["buy_count"] += 1
    elif sig["signal"].startswith("SELL"):
        DB["stats"]["sell_count"] += 1
    else:
        DB["stats"]["wait_count"] += 1

    if auto:
        DB["stats"]["total_signals_sent_auto"] += 1
    else:
        DB["stats"]["total_signals_sent_manual"] += 1

    save_db(DB)

# =========================================================
# تنسيق الرسائل
# =========================================================
def format_start_message(record: Dict[str, Any]) -> str:
    vip_text = "مشترك ✅" if is_vip(record) else "غير مشترك"
    auto_text = "مفعل ✅" if record.get("auto_signals", False) and is_vip(record) else "غير مفعل ❌"

    return (
        "🔥 أهلاً بك في Abod Gold Bot\n\n"
        "بوت إشارات ذهب مطور لتقليل العشوائية وتحسين الدقة.\n\n"
        f"📌 حالتك: {'VIP' if is_vip(record) else 'مجاني'}\n"
        f"🎁 المجاني المتبقي: {free_left(record)}\n"
        f"🏆 الاشتراك: {vip_text}\n"
        f"🤖 الإشارات التلقائية: {auto_text}\n\n"
        "الأوامر:\n"
        "/signal\n"
        "/price\n"
        "/vip\n"
        "/autosignal\n"
        "/id\n"
        "/stats"
    )

def format_signal_message(sig: Dict[str, Any], auto: bool = False) -> str:
    prefix = "🤖 إشارة تلقائية للمشتركين\n\n" if auto else "📡 إشارة الذهب الآن\n\n"

    if sig["signal"].startswith("WAIT"):
        return (
            prefix
            f"النوع: {sig['signal']}\n"
            f"السعر الحالي: {sig['entry']}\n"
            f"القوة التقريبية: {sig['score']}%\n"
            f"EMA9: {sig['ema9']}\n"
            f"EMA21: {sig['ema21']}\n"
            f"EMA50: {sig['ema50']}\n"
            f"RSI: {sig['rsi']}\n"
            f"ATR: {sig['atr']}\n\n"
            f"📝 السبب: {sig['reason']}\n"
            f"🕒 الوقت: {sig['time']}"
        )

    return (
        prefix
        f"النوع: {sig['signal']}\n"
        f"سعر الدخول: {sig['entry']}\n"
        f"وقف الخسارة: {sig['sl']}\n"
        f"الهدف 1: {sig['tp1']}\n"
        f"الهدف 2: {sig['tp2']}\n\n"
        f"القوة التقريبية: {sig['score']}%\n"
        f"EMA9: {sig['ema9']}\n"
        f"EMA21: {sig['ema21']}\n"
        f"EMA50: {sig['ema50']}\n"
        f"RSI: {sig['rsi']}\n"
        f"ATR: {sig['atr']}\n\n"
        f"📝 السبب: {sig['reason']}\n"
        f"🕒 الوقت: {sig['time']}"
    )

def format_stats_message() -> str:
    return (
        "📈 إحصائيات البوت\n\n"
        f"👥 عدد المستخدمين: {count_total_users()}\n"
        f"💎 عدد المشتركين VIP: {count_vip_users()}\n"
        f"🤖 مفعلين التلقائي: {count_auto_users()}\n\n"
        f"📡 إشارات يدوية مرسلة: {DB['stats']['total_signals_sent_manual']}\n"
        f"🤖 إشارات تلقائية مرسلة: {DB['stats']['total_signals_sent_auto']}\n\n"
        f"🟢 BUY: {DB['stats']['buy_count']}\n"
        f"🔴 SELL: {DB['stats']['sell_count']}\n"
        f"🟡 WAIT: {DB['stats']['wait_count']}"
    )

# =========================================================
# حماية التكرار
# =========================================================
def check_signal_cooldown(record: Dict[str, Any]) -> Tuple[bool, int]:
    last_time = int(record.get("last_signal_time", 0))
    now_ts = int(time.time())
    diff = now_ts - last_time

    if diff < SIGNAL_COOLDOWN_SECONDS:
        return False, SIGNAL_COOLDOWN_SECONDS - diff
    return True, 0

def update_signal_time(record: Dict[str, Any]) -> None:
    record["last_signal_time"] = int(time.time())

# =========================================================
# الأوامر العامة
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    record = get_user_record(update.effective_user.id)
    await update.message.reply_text(
        format_start_message(record),
        reply_markup=main_keyboard()
    )

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        price, symbol = get_current_price()
        await update.message.reply_text(
            f"📊 سعر الذهب الحالي:\n\n{price} USD\nالمصدر: {symbol}",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        logger.error(f"price_command error: {e}")
        await update.message.reply_text(
            f"❌ فشل جلب السعر.\n{e}",
            reply_markup=main_keyboard()
        )

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    record = get_user_record(user_id)

    ok, seconds_left = check_signal_cooldown(record)
    if not ok:
        await update.message.reply_text(
            f"⏳ انتظر {seconds_left} ثانية ثم اطلب إشارة جديدة.",
            reply_markup=main_keyboard()
        )
        return

    if not is_vip(record) and free_left(record) <= 0:
        await update.message.reply_text(
            "❌ انتهت الإشارات المجانية.\nاشترك VIP لتكمل.",
            reply_markup=main_keyboard()
        )
        return

    try:
        sig = build_signal()

        if not is_vip(record):
            record["free_signals_used"] = int(record.get("free_signals_used", 0)) + 1

        update_signal_time(record)
        DB["users"][str(user_id)] = record
        update_signal_stats(sig, auto=False)
        save_db(DB)

        await update.message.reply_text(
            format_signal_message(sig, auto=False),
            reply_markup=main_keyboard()
        )
    except Exception as e:
        logger.error(f"signal_command error: {e}")
        await update.message.reply_text(
            f"❌ فشل توليد الإشارة.\n{e}",
            reply_markup=main_keyboard()
        )

async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "💎 الاشتراك VIP\n\nللتفعيل أو التجديد تواصل مع الدعم.",
        reply_markup=support_keyboard()
    )

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🎁 الباقات:\n\n"
        "1 شهر = 30$\n"
        "3 أشهر = 75$\n"
        "6 أشهر = 140$\n\n"
        "للاشتراك تواصل مع الدعم.",
        reply_markup=support_keyboard()
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"🆔 الأيدي الخاص بك:\n{update.effective_user.id}",
        reply_markup=main_keyboard()
    )

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"📞 التواصل:\n@{OWNER_USERNAME}",
        reply_markup=support_keyboard()
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        format_stats_message(),
        reply_markup=main_keyboard()
    )

async def autosignal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    record = get_user_record(user_id)

    if not is_vip(record):
        await update.message.reply_text(
            "❌ الإشارات التلقائية للمشتركين VIP فقط.",
            reply_markup=main_keyboard()
        )
        return

    record["auto_signals"] = not record.get("auto_signals", False)
    DB["users"][str(user_id)] = record
    save_db(DB)

    status = "تم التفعيل ✅" if record["auto_signals"] else "تم الإيقاف ❌"
    await update.message.reply_text(
        f"🤖 الإشارات التلقائية: {status}",
        reply_markup=main_keyboard()
    )

# =========================================================
# أوامر المالك
# =========================================================
def owner_only(user_id: int) -> bool:
    return user_id == OWNER_ID

async def addvip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id):
        return

    try:
        target_id = int(context.args[0])
        days = int(context.args[1])

        rec = get_user_record(target_id)
        now = datetime.now()

        current_vip = rec.get("vip_until")
        if current_vip:
            try:
                current_dt = datetime.fromisoformat(current_vip)
                base = current_dt if current_dt > now else now
            except Exception:
                base = now
        else:
            base = now

        rec["vip_until"] = (base + timedelta(days=days)).isoformat()
        DB["users"][str(target_id)] = rec
        save_db(DB)

        await update.message.reply_text(f"✅ تم تفعيل VIP للمستخدم {target_id} لمدة {days} يوم.")
    except Exception as e:
        await update.message.reply_text(f"❌ الاستخدام:\n/addvip USER_ID DAYS\n\nالخطأ: {e}")

async def removevip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id):
        return

    try:
        target_id = int(context.args[0])
        rec = get_user_record(target_id)
        rec["vip_until"] = None
        rec["auto_signals"] = False
        DB["users"][str(target_id)] = rec
        save_db(DB)

        await update.message.reply_text(f"✅ تم حذف VIP من المستخدم {target_id}.")
    except Exception as e:
        await update.message.reply_text(f"❌ الاستخدام:\n/removevip USER_ID\n\nالخطأ: {e}")

async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id):
        return

    try:
        target_id = int(context.args[0])
        rec = get_user_record(target_id)

        await update.message.reply_text(
            "🧾 معلومات المستخدم\n\n"
            f"ID: {target_id}\n"
            f"free_signals_used: {rec.get('free_signals_used')}\n"
            f"vip_until: {rec.get('vip_until')}\n"
            f"auto_signals: {rec.get('auto_signals')}\n"
            f"joined_at: {rec.get('joined_at')}\n"
            f"last_signal_time: {rec.get('last_signal_time')}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ الاستخدام:\n/userinfo USER_ID\n\nالخطأ: {e}")

async def adminstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id):
        return

    await update.message.reply_text(format_stats_message())

# =========================================================
# الإشارات التلقائية للمشتركين
# =========================================================
async def auto_signal_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    vip_targets = []

    for uid, rec in DB["users"].items():
        if is_vip(rec) and rec.get("auto_signals", False):
            vip_targets.append(int(uid))

    if not vip_targets:
        logger.info("No VIP users with auto signals enabled.")
        return

    try:
        sig = build_signal()
        text = format_signal_message(sig, auto=True)

        success_count = 0
        for uid in vip_targets:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                success_count += 1
            except Exception as send_err:
                logger.error(f"Failed to send auto signal to {uid}: {send_err}")

        if success_count > 0:
            update_signal_stats(sig, auto=True)
            logger.info(f"Auto signal sent to {success_count} users.")

    except Exception as e:
        logger.error(f"auto_signal_job error: {e}")

# =========================================================
# أزرار النص
# =========================================================
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if text == "📡 إشارة الآن":
        await signal_command(update, context)
    elif text == "📊 السعر":
        await price_command(update, context)
    elif text == "💎 الاشتراك":
        await vip_command(update, context)
    elif text == "🎁 الباقات":
        await plans_command(update, context)
    elif text == "🤖 التلقائي":
        await autosignal_command(update, context)
    elif text == "🆔 الأيدي":
        await id_command(update, context)
    elif text == "📈 الإحصائيات":
        await stats_command(update, context)
    elif text == "📞 تواصل":
        await contact_command(update, context)

# =========================================================
# الأخطاء
# =========================================================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)

# =========================================================
# التشغيل
# =========================================================
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price_command))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CommandHandler("autosignal", autosignal_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # أوامر المالك
    app.add_handler(CommandHandler("addvip", addvip_command))
    app.add_handler(CommandHandler("removevip", removevip_command))
    app.add_handler(CommandHandler("userinfo", userinfo_command))
    app.add_handler(CommandHandler("adminstats", adminstats_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_error_handler(error_handler)

    # جدولة الإشارات التلقائية
    app.job_queue.run_repeating(
        auto_signal_job,
        interval=AUTO_SIGNAL_INTERVAL_MINUTES * 60,
        first=60,
        name="auto_gold_signals"
    )

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
