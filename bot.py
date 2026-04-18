import json
import os
import logging
from datetime import datetime, timedelta

import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# الإعدادات
# =========================
BOT_TOKEN = "8749740785:AAE2Yui9tdlxx_pzp40fRU_BhlEYQHEtvhY"

OWNER_NAME = "Abod"
OWNER_USERNAME = "@Abod_gold"
OWNER_ID = 5322650589  # حط ايديك هون

DATA_FILE = "users.json"
FREE_LIMIT = 2

# =========================
# لوج
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# تحميل البيانات
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# =========================
# جلب سعر الذهب
# =========================
def get_gold_price():
    try:
        data = yf.download("XAUUSD=X", period="1d", interval="5m")
        return float(data["Close"].iloc[-1])
    except:
        return None

# =========================
# تحليل بسيط
# =========================
def get_signal():
    try:
        df = yf.download("XAUUSD=X", period="5d", interval="15m")

        df["EMA9"] = df["Close"].ewm(span=9).mean()
        df["EMA21"] = df["Close"].ewm(span=21).mean()

        last = df.iloc[-1]

        price = last["Close"]
        ema9 = last["EMA9"]
        ema21 = last["EMA21"]

        if ema9 > ema21:
            signal = "BUY 🟢"
            sl = price - 2
            tp = price + 4
        else:
            signal = "SELL 🔴"
            sl = price + 2
            tp = price - 4

        return signal, price, sl, tp
    except:
        return None, None, None, None

# =========================
# /start
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    data = load_data()
    if user_id not in data:
        data[user_id] = {
            "used": 0,
            "vip": False
        }
        save_data(data)

    await update.message.reply_text(
        f"🔥 أهلاً في بوت الذهب\n\n"
        f"أول صفقتين مجاناً 🎁\n"
        f"بعدها اشتراك VIP\n\n"
        f"👤 {OWNER_USERNAME}"
    )

# =========================
# /price
# =========================
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = get_gold_price()

    if price is None:
        await update.message.reply_text("❌ فشل جلب السعر")
        return

    await update.message.reply_text(
        f"📊 سعر الذهب الآن:\n{price}\n\n👤 {OWNER_USERNAME}"
    )

# =========================
# /signal
# =========================
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()

    if user_id not in data:
        data[user_id] = {"used": 0, "vip": False}

    user = data[user_id]

    if not user["vip"] and user["used"] >= FREE_LIMIT:
        await update.message.reply_text(
            "❌ انتهت المجانية\nتواصل للاشتراك VIP\n"
            f"{OWNER_USERNAME}"
        )
        return

    sig, price, sl, tp = get_signal()

    if sig is None:
        await update.message.reply_text("❌ فشل التحليل")
        return

    if not user["vip"]:
        user["used"] += 1
        save_data(data)

    await update.message.reply_text(
        f"📡 إشارة ذهب\n\n"
        f"{sig}\n"
        f"Entry: {price}\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n\n"
        f"👤 {OWNER_USERNAME}"
    )

# =========================
# /addvip (لصاحب البوت فقط)
# =========================
async def addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    try:
        user_id = context.args[0]
    except:
        await update.message.reply_text("❌ اكتب الايدي")
        return

    data = load_data()

    if user_id not in data:
        data[user_id] = {"used": 0, "vip": True}
    else:
        data[user_id]["vip"] = True

    save_data(data)

    await update.message.reply_text("✅ تم تفعيل VIP")

# =========================
# تشغيل البوت
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("addvip", addvip))

print("🚀 Bot Running...")
app.run_polling()
