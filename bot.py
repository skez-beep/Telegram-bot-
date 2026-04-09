import os
import json
from datetime import datetime, timedelta
import requests

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


# =========================
# الإعدادات
# =========================
BOT_TOKEN = "8749740785:AAGuy3TA2jb-SQ1xt9-VJ1X0sG0A7yk17No"
TD_API_KEY = "222eba84b1384bfb9bcaadb88381b9a6"

CONTACT_USERNAME = "Abod_gold"
ADMIN_USER_ID = 123456789  # 🔥 حط ID تبعك هون


DATA_FILE = "data.json"


# =========================
# التخزين
# =========================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


db = load_data()


def get_user(user_id):
    users = db["users"]
    if str(user_id) not in users:
        users[str(user_id)] = {
            "free": 0,
            "vip": None
        }
    return users[str(user_id)]


def is_vip(user):
    if not user["vip"]:
        return False
    return datetime.utcnow() < datetime.fromisoformat(user["vip"])


# =========================
# API
# =========================
def fetch():
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": "XAU/USD",
        "interval": "1min",
        "outputsize": 100,
        "apikey": TD_API_KEY
    }

    r = requests.get(url)
    data = r.json()

    values = list(reversed(data["values"]))

    candles = []
    for v in values:
        candles.append({
            "high": float(v["high"]),
            "low": float(v["low"]),
            "close": float(v["close"])
        })

    return candles


# =========================
# مؤشرات
# =========================
def ema(values, p):
    k = 2 / (p + 1)
    e = sum(values[:p]) / p
    for v in values[p:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values, p=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    g = sum(gains[:p]) / p
    l = sum(losses[:p]) / p

    if l == 0:
        return 100

    rs = g / l
    return 100 - (100 / (1 + rs))


def atr(candles, p=14):
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i-1]["close"]

        tr = max(h-l, abs(h-pc), abs(l-pc))
        trs.append(tr)

    a = sum(trs[:p]) / p
    for tr in trs[p:]:
        a = (a * (p-1) + tr) / p
    return a


def adx(candles, p=14):
    trs, plus, minus = [], [], []

    for i in range(1, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        ph, pl = candles[i-1]["high"], candles[i-1]["low"]

        up = h - ph
        down = pl - l

        plus.append(up if up > down and up > 0 else 0)
        minus.append(down if down > up and down > 0 else 0)

        trs.append(max(h-l, abs(h-candles[i-1]["close"]), abs(l-candles[i-1]["close"])))

    tr14 = sum(trs[:p])
    p14 = sum(plus[:p])
    m14 = sum(minus[:p])

    dxs = []

    for i in range(p, len(trs)):
        tr14 = tr14 - tr14/p + trs[i]
        p14 = p14 - p14/p + plus[i]
        m14 = m14 - m14/p + minus[i]

        if tr14 == 0:
            continue

        pdi = 100 * p14 / tr14
        mdi = 100 * m14 / tr14

        if pdi + mdi == 0:
            continue

        dx = 100 * abs(pdi - mdi) / (pdi + mdi)
        dxs.append(dx)

    if len(dxs) < p:
        return None

    a = sum(dxs[:p]) / p
    for dx in dxs[p:]:
        a = (a * (p-1) + dx) / p

    return a


# =========================
# تحليل
# =========================
def build_signal():
    candles = fetch()
    closes = [c["close"] for c in candles]

    price = closes[-1]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    r = rsi(closes)
    a = atr(candles)
    d = adx(candles)

    signal = "NONE"
    entry = round(price, 2)
    sl = tp1 = tp2 = None

    if ema9 > ema21 and r > 55 and d > 25:
        signal = "BUY 🟢 (سكالب)"
        sl = round(entry - a*1.5, 2)
        tp1 = round(entry + a*1.5, 2)
        tp2 = round(entry + a*2, 2)

    elif ema9 < ema21 and r < 45 and d > 25:
        signal = "SELL 🔴 (سكالب)"
        sl = round(entry + a*1.5, 2)
        tp1 = round(entry - a*1.5, 2)
        tp2 = round(entry - a*2, 2)

    return {
        "price": entry,
        "ema9": round(ema9,2),
        "ema21": round(ema21,2),
        "rsi": round(r,2),
        "adx": round(d,2),
        "atr": round(a,2),
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2
    }


def format_signal(s):
    if s["signal"] == "NONE":
        return f"📊 تحليل الذهب\n\n🟡 السعر: {s['price']}\n\n⏳ لا توجد صفقة\n\n✉️ @{CONTACT_USERNAME}"

    return f"""🔥 صفقة سكالب

🟡 السعر: {s['price']}

📢 {s['signal']}
🎯 Entry: {s['entry']}
🛑 SL: {s['sl']}
💰 TP1: {s['tp1']}
💰 TP2: {s['tp2']}

✉️ @{CONTACT_USERNAME}
"""


# =========================
# أوامر
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 أهلاً في بوت الذهب\nاستخدم /signal")


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)

    if not is_vip(user) and user["free"] >= 2:
        await update.message.reply_text(f"❌ انتهى المجاني\nتواصل @{CONTACT_USERNAME}")
        return

    s = build_signal()

    if not is_vip(user):
        user["free"] += 1
        save_data(db)

    await update.message.reply_text(format_signal(s))


async def grantvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return

    uid = int(context.args[0])
    days = int(context.args[1])

    user = get_user(uid)
    user["vip"] = (datetime.utcnow() + timedelta(days=days)).isoformat()

    save_data(db)
    await update.message.reply_text("تم تفعيل VIP")


# =========================
# تشغيل
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("grantvip", grantvip))

print("RUNNING...")
app.run_polling()
