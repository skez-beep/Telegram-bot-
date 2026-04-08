from telegram.ext import MessageHandler, filters

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"وصلني: {text}")

app.add_handler(MessageHandler(filters.TEXT, handle_message))
