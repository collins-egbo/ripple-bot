import os
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Load environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID", 0))  # your group ID
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")    # full URL Render will call

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")
if GROUP_ID == 0:
    raise ValueError("GROUP_ID is not set or invalid in environment variables")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set in environment variables")

# Command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is running with webhook.")

# Welcome new members
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Welcome {member.full_name}! Please start the bot in private chat using /start."
        )

# Example echo handler
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"You said: {update.message.text}")

async def main():
    # Build and initialize app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await app.initialize()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Start webhook
    await app.start_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=WEBHOOK_URL
    )

    print("✅ Webhook bot is running...")

    # Keep bot running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
