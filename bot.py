import os
from datetime import datetime, time, timedelta, date
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---- Env vars ----
BOT_TOKEN = os.environ["BOT_TOKEN"]                     # required
GROUP_ID = int(os.environ["GROUP_ID"])                  # required
WEBHOOK_BASE = os.environ["WEBHOOK_BASE"]               # required, e.g. https://ripple-bot.onrender.com
PORT = int(os.environ.get("PORT", "10000"))             # Render will expose this port
TZ_NAME = os.environ.get("TZ", "Europe/Amsterdam")      # your timezone for jobs
TZ = ZoneInfo(TZ_NAME)

# ---- In-memory storage (MVP) ----
# replies_by_day[date] = { user_id: {"name": str, "text": str} }
replies_by_day: dict[date, dict[int, dict]] = {}

# ===== Handlers =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private /start."""
    user = update.effective_user
    await update.message.reply_text(
        f"Hello {user.first_name}! 👋 Ripple bot is running.\n"
        "You’ll get prompts in the group. Please reply to me here (privately)."
    )

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message in group when someone joins."""
    for member in update.message.new_chat_members:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=(
                f"👋 Welcome {member.full_name}!\n"
                "To participate, open a private chat with me and send /start."
            )
        )

async def collect_private_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect private replies for today's prompt."""
    if update.effective_chat.type != "private":
        return
    today = datetime.now(tz=TZ).date()
    user = update.effective_user
    text = (update.message.text or "").strip()
    if not text:
        return

    if today not in replies_by_day:
        replies_by_day[today] = {}

    replies_by_day[today][user.id] = {"name": user.first_name or "Friend", "text": text}
    await update.message.reply_text("✅ Got it! You’ll see others’ answers at reveal time.")

# ===== Jobs (run with JobQueue) =====

async def job_send_prompt(context: ContextTypes.DEFAULT_TYPE):
    """Send daily prompt in the group and reset TODAY's answers."""
    today = datetime.now(tz=TZ).date()
    # Start a fresh bucket for today
    replies_by_day[today] = {}

    prompt_text = (
        "🎙️ *Prompt of the day*\n\n"
        "What made you smile today?\n\n"
        "👉 Reply to me *privately* (open my DM) so your answer stays hidden until reveal."
    )
    await context.bot.send_message(chat_id=GROUP_ID, text=prompt_text, parse_mode="Markdown")

async def job_reveal_answers(context: ContextTypes.DEFAULT_TYPE):
    """Reveal YESTERDAY's answers – only to participants who replied."""
    today = datetime.now(tz=TZ).date()
    yesterday = today - timedelta(days=1)

    bucket = replies_by_day.get(yesterday) or {}
    if not bucket:
        # Nothing to reveal – notify the group (optional)
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text="⏰ Time’s up! No answers to reveal from yesterday."
        )
        return

    # For each participant, DM them everyone else's answers
    for uid, me in bucket.items():
        others = [f"• {info['name']}: {info['text']}" for u2, info in bucket.items() if u2 != uid]
        if not others:
            # They were the only respondent
            await context.bot.send_message(
                chat_id=uid,
                text="⏰ Reveal time! You were the only one who replied yesterday."
            )
        else:
            await context.bot.send_message(
                chat_id=uid,
                text="⏰ *Reveal time!* Here are others’ answers:\n\n" + "\n".join(others),
                parse_mode="Markdown"
            )

    # (Optional) group summary
    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=f"💬 Reveal complete! {len(bucket)} participant(s) replied yesterday."
    )

# ===== Main (webhook + jobs) =====

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND), collect_private_reply))

    # JobQueue – schedule daily jobs in your timezone
    jq = app.job_queue
    # Prompt every day at 20:00 local time
    jq.run_daily(job_send_prompt, time=time(20, 0, tzinfo=TZ), name="daily_prompt")
    # Reveal every day at 18:00 local time (reveals yesterday’s replies)
    jq.run_daily(job_reveal_answers, time=time(18, 0, tzinfo=TZ), name="daily_reveal")

    # Webhook URL must include a path (Telegram requires a concrete path)
    # We'll use the token as the secret path.
    full_webhook_url = f"{WEBHOOK_BASE.rstrip('/')}/{BOT_TOKEN}"

    # PTB 21.5: run_webhook handles initialize/start + aiohttp server under the hood
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,          # must match the path in full_webhook_url
        webhook_url=full_webhook_url # public URL Telegram will call
    )

if __name__ == "__main__":
    main()
