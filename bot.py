from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import random

TOKEN = "8749740785:AAHsZfdv6B3tzIcTEIdnnHFFjVLsJAt2OWo"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 أهلاً في بوت الذهب 🔥\n\n"
        "الأوامر المتاحة:\n"
        "/start - تشغيل البوت\n"
        "/signal - إشارة تجريبية\n"
        "/price - سعر الذهب\n"
        "/vip - معلومات الاشتراك"
    )

async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    signals = [
        "🟢 شراء الذهب من 2320\n🎯 الهدف: 2335\n🛑 وقف: 2310",
        "🔴 بيع الذهب من 2340\n🎯 الهدف: 2325\n🛑 وقف: 2350",
        "🟢 شراء الذهب من 2315\n🎯 الهدف: 2330\n🛑 وقف: 2305"
    ]
    await update.message.reply_text(random.choice(signals))

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 سعر الذهب\n\n"
        "سيتم قريباً ربط البوت بسعر الذهب الحقيقي مباشر.\n"
        "تابع /signal و /vip"
    )

async def vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 اشتراك VIP\n\n"
        "أول صفقتين مجاناً.\n"
        "بعدها يتم تفعيل الاشتراك المدفوع.\n"
        "للتفاصيل تواصل مع الإدارة."
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("signal", signal))
app.add_handler(CommandHandler("price", price))
app.add_handler(CommandHandler("vip", vip))

app.run_polling()
