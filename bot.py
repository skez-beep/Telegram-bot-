from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8749740785:AAHsZfdv6B3tzIcTEIdnnHFFjVLsJAt2OWo"

user_signals = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 بوت إشارات الذهب\n\n"
        "💰 أول صفقتين مجاناً\n"
        "⚡ إشارات سريعة\n\n"
        "الأوامر:\n"
        "/price\n"
        "/signal\n"
        "/vip\n"
        "/help"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 سعر الذهب\n\n"
        "سيتم قريباً ربط البوت بسعر الذهب الحقيقي مباشر.\n"
        "تابع /signal و /vip"
    )

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in user_signals:
        user_signals[user_id] = 0

    if user_signals[user_id] >= 2:
        await update.message.reply_text(
            "🔒 انتهت الإشارات المجانية\n\n"
            "💎 للاشتراك VIP:\n"
            "@Abod_gold"
        )
        return

    user_signals[user_id] += 1

    await update.message.reply_text(
        f"📊 إشارة مجانية رقم {user_signals[user_id]}\n\n"
        "🟢 BUY\n"
        "💰 دخول: 2320\n"
        "🎯 هدف: 2335\n"
        "⛔ وقف: 2310\n\n"
        "⚠️ بعد إشارتين لازم تشترك VIP"
    )

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 الاشتراك VIP\n\n"
        "📩 للتواصل:\n"
        "@Abod_gold"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر:\n"
        "/price\n"
        "/signal\n"
        "/vip\n"
        "/help"
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("vip", vip))
app.add_handler(CommandHandler("help", help_command))

app.run_polling()
