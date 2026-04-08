import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("8749740785:AAE_CFVKqmi7sQNeDYwo7Y2yajYYkXWUHYg")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 أهلاً في بوت الذهب\n\n"
        "الأوامر:\n"
        "/price - سعر الذهب\n"
        "/signal - إشارة تجريبية\n"
        "/vip - الاشتراك VIP\n"
        "/help - المساعدة"
    )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 سعر الذهب حالياً: قريباً سيتم ربطه بسعر مباشر")

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📍 إشارة تجريبية:\n"
        "النوع: BUY\n"
        "الدخول: 3330\n"
        "الهدف: 3340\n"
        "الوقف: 3323\n\n"
        "⚠️ هذه إشارة تجريبية فقط"
    )

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 VIP\n"
        "للاشتراك في النسخة المدفوعة تواصل مع الإدارة.\n"
        "المميزات:\n"
        "- إشارات أكثر\n"
        "- تنبيهات أسرع\n"
        "- نقاط دخول ووقف وهدف"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("استخدم: /price /signal /vip /help")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("vip", vip))
app.add_handler(CommandHandler("help", help_command))

app.run_polling()
