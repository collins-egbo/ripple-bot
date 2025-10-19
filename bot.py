import os
import json
import random
from datetime import time, datetime, timedelta
from pytz import timezone
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters, CallbackContext
)

# =========================
# 🔧 CONFIGURATION
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
MAIN_GROUP_ID = int(os.environ["GROUP_ID"])
TIMEZONE = timezone("Europe/Amsterdam")

# Render-specific (for webhooks)
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", "10000"))

# --- 🧪 TEST SCHEDULE (all today, Amsterdam time) ---
# Adjust these times for your local timezone testing
PROMPT_TIME    = time(11, 40, tzinfo=TIMEZONE)   # Show prompt at 11:40
REMINDER_TIME  = time(11, 45, tzinfo=TIMEZONE)   # Reminder at 11:45
REVEAL_TIME    = time(12, 0,  tzinfo=TIMEZONE)   # Reveal at 12:00
CLEANUP_TIME   = time(12, 20, tzinfo=TIMEZONE)   # Cleanup at 12:20

# Files for persistence (ephemeral on Render)
USED_PROMPTS_FILE = "used_prompts.json"
DISCUSSION_FILE   = "discussion_group.json"
REPLIES_FILE      = "replies.json"

# =========================
# 📋 PROMPTS
# =========================

PROMPTS = [
    {"topic": "Mental Wellbeing", "text": "What’s one small thing that secretly keeps you sane when life gets messy?"},
    {"topic": "Fun Memories", "text": "What’s a memory with this group that instantly makes you grin?"},
    {"topic": "Future Plans", "text": "If this group planned a trip together, where would we end up — and who’s getting lost first?"},
]

# =========================
# 📦 UTILITIES
# =========================

def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f)

def get_daily_prompt():
    used_indices = load_json(USED_PROMPTS_FILE).get("used", [])
    if len(used_indices) >= len(PROMPTS):
        used_indices = []
    available = [i for i in range(len(PROMPTS)) if i not in used_indices]
    chosen_index = random.choice(available)
    used_indices.append(chosen_index)
    save_json(USED_PROMPTS_FILE, {"used": used_indices})
    chosen = PROMPTS[chosen_index]
    return f"🌞 *Daily Prompt*\n🧭 *Topic:* {chosen['topic']}\n💬 *Prompt:* {chosen['text']}"

def get_discussion_chat_id() -> int | None:
    data = load_json(DISCUSSION_FILE)
    cid = data.get("chat_id")
    return int(cid) if cid is not None else None

def set_discussion_chat_id(chat_id: int):
    save_json(DISCUSSION_FILE, {"chat_id": int(chat_id)})

# =========================
# 💬 HANDLERS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey there! 🧪 Test mode active.\n"
        "Prompt at 11:40 → Reminder 11:45 → Reveal 12:00 → Cleanup 12:20.\n"
        "Reply to me *privately* to join the reveal. 💬",
        parse_mode="Markdown"
    )

async def collect_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    replies = load_json(REPLIES_FILE)
    user_id = str(update.message.from_user.id)
    replies[user_id] = update.message.to_dict()
    save_json(REPLIES_FILE, replies)
    await update.message.reply_text("Got it! Your reply’s saved for today’s test round 💬")

async def set_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Run this in the *group* you want to use for discussions.", parse_mode="Markdown")
        return
    set_discussion_chat_id(chat.id)
    await update.message.reply_text("✅ This group is now set as the test discussion space.")

# =========================
# ⏰ SCHEDULED JOBS
# =========================

async def send_daily_prompt(context: CallbackContext):
    bot = context.bot
    prompt = get_daily_prompt()
    try:
        chat = await bot.get_chat(MAIN_GROUP_ID)
        if chat.pinned_message:
            await bot.unpin_chat_message(chat_id=MAIN_GROUP_ID)
    except Exception as e:
        print("Unpin error:", e)

    text = (
        f"{prompt}\n\n"
        "📝 *How it works (TEST MODE):*\n"
        "• Reply to me *in private* (text or voice).\n"
        "• Reveal at *12:00*.\n"
        "• Discussion clears at *12:20*. 💬"
    )
    msg = await bot.send_message(chat_id=MAIN_GROUP_ID, text=text, parse_mode="Markdown")
    try:
        await bot.pin_chat_message(chat_id=MAIN_GROUP_ID, message_id=msg.message_id)
    except Exception as e:
        print("Pin error:", e)

async def last_hour_reminder(context: CallbackContext):
    await context.bot.send_message(
        chat_id=MAIN_GROUP_ID,
        text="⏳ *Reminder:* Last few minutes to reply privately before the reveal at *12:00*!",
        parse_mode="Markdown"
    )

async def reveal_replies(context: CallbackContext):
    replies = load_json(REPLIES_FILE)
    bot = context.bot
    discussion_id = get_discussion_chat_id() or MAIN_GROUP_ID

    if not replies:
        await bot.send_message(discussion_id, "No replies received for this test. 😶")
        return

    await bot.send_message(
        discussion_id,
        "🔓 *Test Reveal!* Here are today’s test replies — chat freely until 12:20 💬",
        parse_mode="Markdown"
    )

    for uid, msg in replies.items():
        try:
            await bot.forward_message(
                chat_id=discussion_id,
                from_chat_id=int(uid),
                message_id=msg["message_id"]
            )
        except Exception:
            user = msg.get("from", {}).get("first_name", "Someone")
            text = msg.get("text")
            if text:
                await bot.send_message(
                    chat_id=discussion_id,
                    text=f"💬 *{user} said:* {text}",
                    parse_mode="Markdown"
                )

    save_json(REPLIES_FILE, {})

async def cleanup_discussion(context: CallbackContext):
    discussion_id = get_discussion_chat_id() or MAIN_GROUP_ID
    try:
        await context.bot.send_message(
            chat_id=discussion_id,
            text="🧹 Test discussion closed. Everything worked!"
        )
    except Exception:
        pass

# =========================
# 🕒 COMMAND: /nexttimes
# =========================
async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🕒 *Test schedule (Amsterdam)*\n"
        f"• Prompt: {PROMPT_TIME.strftime('%H:%M')}\n"
        f"• Reminder: {REMINDER_TIME.strftime('%H:%M')}\n"
        f"• Reveal: {REVEAL_TIME.strftime('%H:%M')}\n"
        f"• Cleanup: {CLEANUP_TIME.strftime('%H:%M')}",
        parse_mode="Markdown"
    )

# =========================
# 🚀 MAIN — WEBHOOK MODE (Render)
# =========================
def main():
    if not RENDER_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL is not set — Render provides this automatically.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nexttimes", show_schedule))
    app.add_handler(CommandHandler("setdiscussion", set_discussion))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.VOICE), collect_reply))

    # Jobs (test)
    jq = app.job_queue
    jq.run_daily(send_daily_prompt,  time=PROMPT_TIME,  name="prompt")
    jq.run_daily(last_hour_reminder, time=REMINDER_TIME, name="reminder")
    jq.run_daily(reveal_replies,     time=REVEAL_TIME,   name="reveal")
    jq.run_daily(cleanup_discussion, time=CLEANUP_TIME,  name="cleanup")

    webhook_path = BOT_TOKEN
    webhook_url = f"{RENDER_URL.rstrip('/')}/{webhook_path}"
    print(f"✅ Webhook listening on port {PORT}, URL: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
