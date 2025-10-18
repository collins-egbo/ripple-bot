import asyncio
from datetime import datetime, time, timedelta
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Your bot info ---
GROUP_ID = -4835689810
BOT_TOKEN = "8423848587:AAFtCyG5TdP_nFJwChWPeOxNEDPr_n-uj1w"

# --- Track users who already started the bot ---
announced_users = set()


# --- Bot commands ---
async def start(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    # Private confirmation
    await update.message.reply_text(
        f"Hello {user_name}! 👋 Ripple bot is running.\n"
        "You’ll receive your first prompt at 8 PM.\n"
        "Please reply to the bot privately when prompted."
    )

    # Announce in group (only once)
    if user_id not in announced_users:
        announced_users.add(user_id)
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=(
                f"📢 {user_name} has started using Ripple!\n"
                "Everyone, please make sure to start a private chat with the bot and type /start\n"
                "so you can participate in the daily prompts and see others’ replies."
            ),
        )


# --- Notify new members in the group ---
async def new_member_notify(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        user_name = member.first_name

        if user_id not in announced_users:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"👋 Welcome {user_name}!\n"
                    "To participate in Ripple prompts, please start a private chat with me "
                    "and type /start."
                ),
            )


# --- Scheduler tasks ---
async def send_prompt(app):
    await app.bot.send_message(
        chat_id=GROUP_ID, text="🎙️ New prompt! What made you smile today?"
    )


async def reveal_answers(app):
    await app.bot.send_message(
        chat_id=GROUP_ID,
        text="⏰ Time’s up! Everyone who replied can now see the answers 💬",
    )


async def scheduler_loop(app):
    while True:
        now = datetime.now()

        # Schedule prompt at 8 PM
        prompt_time = datetime.combine(now.date(), time(20, 0))
        if now > prompt_time:
            prompt_time += timedelta(days=1)
        wait_seconds = (prompt_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await send_prompt(app)

        # Schedule reveal at 6 PM next day
        now = datetime.now()
        reveal_time = datetime.combine(now.date(), time(18, 0)) + timedelta(days=1)
        wait_seconds = (reveal_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await reveal_answers(app)


# --- Main bot setup ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_notify))

    # Start scheduler safely after polling starts
    async def start_scheduler():
        asyncio.create_task(scheduler_loop(app))

    print("✅ Bot is starting...")
    app.run_polling()
    asyncio.run(start_scheduler())


if __name__ == "__main__":
    main()
