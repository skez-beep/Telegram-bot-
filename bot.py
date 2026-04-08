import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8749740785:AAHsZfdv6B3tzIcTEIdnnHFFjVLsJAt2OWo"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 أهلاً في بوت الذهب\n\n"
        "/price - سعر الذهب\n"
        "/signal - إشارة\n"
        "/vip - اشتراك VIP\n"
        "/help - مساعدة"
    )
async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    user_signals[user_id] = 0  # 👈 هذا السطر المؤقت

    if user_id not in user_signals:
        user_signals[user_id] = 0
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 سعر الذهب\n\n"
        "سيتم قريباً ربط البوت بسعر الذهب الحقيقي مباشر.\n"
        "تابع /signal و /vip"
    )


    )
    )
async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 VIP\n"
        "للاشتراك راسل:\n"
        "@Abod_gold"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("استخدم الأوامر: /price /signal /vip")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("vip", vip))
app.add_handler(CommandHandler("help", help_command))

app.run_polling()
