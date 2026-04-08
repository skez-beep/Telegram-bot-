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

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 سعر الذهب: قريباً")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 إشارة تجريبية\n"
        "BUY\n"
        "دخول: 2320\n"
        "هدف: 2335\n"
        "وقف: 2310"
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
