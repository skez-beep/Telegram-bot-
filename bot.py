from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import random
import requests

TOKEN = "8749740785:AAHsZfdv6B3tzIcTEIdnnHFFjVLsJAt2OWo"

# تخزين عدد الصفقات المجانية لكل مستخدم
free_uses = {}

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    name = user.first_name if user.first_name else "صديقي"
    username = f"@{user.username}" if user.username else "لا يوجد"

    await update.message.reply_text(
        f"🔥 أهلاً {name} في بوت الذهب 🔥\n"
        f"👤 اليوزر: {username}\n\n"
        f"الأوامر:\n"
        f"/signal - إشارة مجانية\n"
        f"/price - سعر الذهب\n"
        f"/vip - اشتراك VIP"
    )

# /signal
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in free_uses:
        free_uses[user_id] = 0

    if free_uses[user_id] >= 2:
        await update.message.reply_text(
            "❌ انتهت الإشارات المجانية\n"
            "💎 للاشتراك VIP:\n@Abod_gold"
        )
        return

    signals = [
        "📈 شراء GOLD من 2300\n🎯 الهدف: 2310\n🛑 وقف: 2290",
        "📉 بيع GOLD من 2310\n🎯 الهدف: 2300\n🛑 وقف: 2320"
    ]

    free_uses[user_id] += 1
    remaining = 2 - free_uses[user_id]

    await update.message.reply_text(
        f"{random.choice(signals)}\n\n"
        f"🎁 المتبقي لك من المجاني: {remaining}\n"
        f"📩 VIP: @Abod_gold"
    )

# /price
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        url = "https://api.metals.live/v1/spot"
        response = requests.get(url)
        data = response.json()

        gold_price = None

        for item in data:
            if item[0] == "gold":
                gold_price = item[1]

        await update.message.reply_text(
            f"📊 سعر الذهب الآن:\n\n🟡 {gold_price} USD"
        )

    except:
        await update.message.reply_text("❌ فشل جلب السعر")

# /vip
async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 اشتراك VIP 🔥\n\n"
        "✔ إشارات دقيقة يومياً\n"
        "✔ فرص ربح عالية\n"
        "✔ متابعة مستمرة\n\n"
        "📩 للتواصل:\n@Abod_gold"
    )

# تشغيل البوت
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("vip", vip))

app.run_polling()
