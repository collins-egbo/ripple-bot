import os
import asyncio
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)

# --- Bot info from environment variables ---
BOT_TOKEN = os.environ["BOT_TOKEN"]  # your Telegram bot token
GROUP_ID = int(os.environ["GROUP_ID"])  # your group id
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # full URL to your Render webhook
PORT = int(os.environ.get("PORT", 8443))  # Render port, default 8443

# --- Bot commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send greeting in private chat."""
    await update.message.reply_text(
        "Hello! 👋 Ripple bot is running.\n"
        "You’ll receive your first prompt at 8 PM.\n"
        "Please reply privately to the bot when prompted."
    )


# --- Scheduler tasks ---
async def send_prompt(app):
    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="🎙️ New prompt! What made you smile today?\n"
             "Reply privately to me!"
    )


async def reveal_answers(app):
    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="⏰ Time’s up! Everyone who replied can now see the answers 💬"
    )


async def scheduler_loop(app):
    """Loop that schedules prompt at 8 PM and reveal at 6 PM next day."""
    while True:
        now = datetime.now()

        # --- Prompt at 8 PM ---
        prompt_time = datetime.combine(now.date(), time(20, 0))
        if now > prompt_time:
            prompt_time += timedelta(days=1)
        await asyncio.sleep((prompt_time - now).total_seconds())
        await send_prompt(app)

        # --- Reveal next day at 6 PM ---
        now = datetime.now()
        reveal_time = datetime.combine(now.date(), time(18, 0)) + timedelta(days=1)
        await asyncio.sleep((reveal_time - now).total_seconds())
        await reveal_answers(app)


# --- Handle new users joining group ---
async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_user = update.chat_member.new_chat_member.user
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=f"👋 Welcome {new_user.full_name}! "
             "Please start the bot in private chat by sending /start."
    )


# --- Main bot setup ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))

    # New members
    app.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))

    # Start the scheduler in the background
    asyncio.create_task(scheduler_loop(app))

    # Run webhook (Render)
    if WEBHOOK_URL:
        await app.start()
        await app.bot.set_webhook(WEBHOOK_URL)
        print("✅ Bot is running on webhook!")
        # Keep running
        await asyncio.Event().wait()
    else:
        print("⚠️ WEBHOOK_URL not set. Running with polling...")
        await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
