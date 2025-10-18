import os
import asyncio
from datetime import datetime, time, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GROUP_ID = -4835689810  # your group chat ID

# --- In-memory storage for demo purposes ---
# You might want to replace with a database for production
user_answers = {}  # {user_id: answer}
answered_users = set()


# --- Bot commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private chat /start command"""
    await update.message.reply_text(
        "Hello! 👋 Ripple bot is running.\n"
        "You’ll receive prompts from the group.\n"
        "Please reply to the bot privately when prompted."
    )


async def new_user_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message in the group when a new user joins"""
    for member in update.message.new_chat_members:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=f"Welcome {member.full_name}! 👋 Please start a private chat with me and send /start."
        )


# --- Scheduler tasks ---
async def send_prompt(app):
    await app.bot.send_message(chat_id=GROUP_ID, text="🎙️ New prompt! What made you smile today?")
    # Reset answers
    user_answers.clear()
    answered_users.clear()


async def reveal_answers(app):
    if not user_answers:
        await app.bot.send_message(chat_id=GROUP_ID, text="⏰ Time’s up! No answers received today.")
        return
    # Send all answers in the group
    text = "⏰ Time’s up! Here are today’s answers:\n\n"
    for user, answer in user_answers.items():
        text += f"{user}: {answer}\n"
    await app.bot.send_message(chat_id=GROUP_ID, text=text)


async def scheduler_loop(app):
    while True:
        now = datetime.now()
        # --- Schedule prompt at 8 PM ---
        prompt_time = datetime.combine(now.date(), time(20, 0))
        if now > prompt_time:
            prompt_time += timedelta(days=1)
        wait_seconds = (prompt_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await send_prompt(app)

        # --- Schedule reveal at 6 PM next day ---
        now = datetime.now()
        reveal_time = datetime.combine(now.date(), time(18, 0)) + timedelta(days=1)
        wait_seconds = (reveal_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await reveal_answers(app)


# --- Private replies handler ---
async def private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store private answers"""
    user_id = update.effective_user.full_name
    text = update.message.text
    if user_id not in answered_users:
        user_answers[user_id] = text
        answered_users.add(user_id)
        await update.message.reply_text("✅ Got it! You can see others’ answers when the reveal happens.")


# --- Main bot setup ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, private_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_user_welcome))

    # Start scheduler safely
    async def start_scheduler():
        asyncio.create_task(scheduler_loop(app))

    # Run webhook for Render deployment
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=WEBHOOK_URL,
        post_init=start_scheduler
    )


if __name__ == "__main__":
    main()
