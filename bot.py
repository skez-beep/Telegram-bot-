from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import random

TOKEN = "8749740785:AAHsZfdv6B3tzIcTEIdnnHFFjVLsJAt2OWo"

# تخزين عدد الصفقات المجانية لكل مستخدم
free_uses = {}

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    name = user.first_name if user.first_name else "صديقي"
    username = f"@{user.username}" if user.username else "ما عندك يوزرنيم"

    await update.message.reply_text(
        f"🔥 أهلاً {name} في بوت الذهب 🔥\n"
        f"👤 اليوزر: {username}\n\n"
        f"الأوامر:\n"
        f"/signal - إشارة مجانية\n"
        f"/vip - الاشتراك VIP"
    )

# /signal
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in free_uses:
        free_uses[user_id] = 0

    # إذا خلص المجاني
    if free_uses[user_id] >= 2:
        await update.message.reply_text(
            "🔒 انتهت الصفقات المجانية.\n\n"
            "📩 للاشتراك VIP تواصل: @Abod_gold"
        )
        return

    signals = [
        "🟢 شراء الذهب من 2320\n🎯 الهدف: 2335\n🛑 وقف: 2310",
        "🔴 بيع الذهب من 2340\n🎯 الهدف: 2325\n🛑 وقف: 2350",
        "🟢 شراء الذهب من 2315\n🎯 الهدف: 2330\n🛑 وقف: 2305"
    ]

    free_uses[user_id] += 1
    remaining = 2 - free_uses[user_id]

    await update.message.reply_text(
        f"{random.choice(signals)}\n\n"
        f"🎁 المتبقي لك من المجاني: {remaining}\n"
        f"📩 VIP: @Abod_gold"
    )

# /vip
async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 اشتراك VIP 🔥\n\n"
        "✔ إشارات دقيقة يومية\n"
        "✔ فرص ربح عالية\n"
        "✔ متابعة مستمرة\n\n"
        "📩 للتواصل والاشتراك:\n"
        "@Abod_gold"
    )

# تشغيل البوت
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("vip", vip))

app.run_polling()
