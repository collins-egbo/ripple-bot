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
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")  # Render sets this automatically for Web Services
PORT = int(os.environ.get("PORT", "10000"))         # Render scans this port; must bind to it

# --- Daily Schedule (editable for testing) ---
PROMPT_TIME    = time(20, 0, tzinfo=TIMEZONE)   # 8:00 PM — new daily prompt
REMINDER_TIME  = time(17, 0, tzinfo=TIMEZONE)   # 5:00 PM — 1-hour-left reminder (before reveal)
REVEAL_TIME    = time(18, 0, tzinfo=TIMEZONE)   # 6:00 PM — reveal + discussion
CLEANUP_TIME   = time(17, 0, tzinfo=TIMEZONE)   # 5:00 PM next day — clean old discussion

# Files for simple persistence (OK on Render's ephemeral disk for this trial)
USED_PROMPTS_FILE = "used_prompts.json"
DISCUSSION_FILE   = "discussion_group.json"   # stores {"chat_id": <int>}
REPLIES_FILE      = "replies.json"            # maps user_id -> last message dict

# =========================
# 📋 PROMPTS
# =========================

PROMPTS = [
    # Mental Wellbeing
    {"topic": "Mental Wellbeing", "text": "What’s one small thing that secretly keeps you sane when life gets messy?"},
    {"topic": "Mental Wellbeing", "text": "When was the last time you took a proper break — like really unplugged — and what did you do?"},
    {"topic": "Mental Wellbeing", "text": "What’s something you’ve started doing lately that makes your days feel lighter?"},
    {"topic": "Mental Wellbeing", "text": "If you could press pause on everything for a day, what would you spend that day doing?"},
    {"topic": "Mental Wellbeing", "text": "Be honest — what’s your brain’s current “weather forecast”? (sunny, foggy, thunderstorms…)"},

    # Fun Memories
    {"topic": "Fun Memories", "text": "What’s a memory with this group that instantly makes you grin?"},
    {"topic": "Fun Memories", "text": "Who in this group is most likely to turn a normal night into a story we’ll tell for years?"},
    {"topic": "Fun Memories", "text": "What’s the dumbest inside joke you still remember?"},
    {"topic": "Fun Memories", "text": "If you could relive one hilarious moment from our past together, which would it be?"},
    {"topic": "Fun Memories", "text": "What’s something funny that happened recently that you wish we’d all been there for?"},

    # Future Plans
    {"topic": "Future Plans", "text": "If this group planned a trip together, where would we end up — and who’s getting lost first?"},
    {"topic": "Future Plans", "text": "What’s one dream you secretly hope you’ll pull off (even if it sounds crazy)?"},
    {"topic": "Future Plans", "text": "If we met again in 10 years, what do you hope your life looks like?"},
    {"topic": "Future Plans", "text": "What’s a skill or hobby you’ve been “meaning to start” forever — be honest!"},
    {"topic": "Future Plans", "text": "If you had to make one bold change in your life before next summer, what would it be?"},
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
        "Hey there! I’ll send a daily question to the group at 8 PM.\n"
        "Reply to me *privately* before 6 PM tomorrow to join the reveal. 💬",
        parse_mode="Markdown"
    )

async def collect_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only accept replies in **private** chat
    if update.effective_chat.type != "private":
        return

    replies = load_json(REPLIES_FILE)
    user_id = str(update.message.from_user.id)
    replies[user_id] = update.message.to_dict()
    save_json(REPLIES_FILE, replies)
    await update.message.reply_text("Got it! Your reply’s saved for today’s round 💬")

async def set_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    One-time setup: run /setdiscussion INSIDE the group you want as the daily discussion space.
    The bot must be a member of that group (and ideally admin to pin, invite, etc).
    """
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Run this in the *group* you want to use for discussions.", parse_mode="Markdown")
        return

    set_discussion_chat_id(chat.id)
    await update.message.reply_text("✅ This group is now set as the daily discussion space.")

# =========================
# ⏰ SCHEDULED JOBS
# =========================

async def send_daily_prompt(context: CallbackContext):
    bot = context.bot
    prompt = get_daily_prompt()

    # Unpin old prompt in main group (best-effort)
    try:
        chat = await bot.get_chat(MAIN_GROUP_ID)
        if chat.pinned_message:
            await bot.unpin_chat_message(chat_id=MAIN_GROUP_ID)
    except Exception as e:
        print("No message to unpin or error:", e)

    # Send and pin new prompt
    text = (
        f"{prompt}\n\n"
        "📝 *How it works:*\n"
        "• Reply to me *in private* (text or voice).\n"
        f"• Deadline: *{REVEAL_TIME.hour}:00 tomorrow*.\n"
        "• At that time, I’ll reveal everyone’s answers in a discussion chat.\n"
        "• You’ll have until *17:00 the next day* to discuss before it resets. 💬"
    )
    msg = await bot.send_message(chat_id=MAIN_GROUP_ID, text=text, parse_mode="Markdown")
    try:
        await bot.pin_chat_message(chat_id=MAIN_GROUP_ID, message_id=msg.message_id)
    except Exception as e:
        print("Error pinning message:", e)

async def last_hour_reminder(context: CallbackContext):
    await context.bot.send_message(
        chat_id=MAIN_GROUP_ID,
        text="⏳ *Last hour to answer today’s prompt!* Reply privately to me before *18:00* to join today’s reveal. 🎧",
        parse_mode="Markdown"
    )

async def reveal_replies(context: CallbackContext):
    replies = load_json(REPLIES_FILE)
    bot = context.bot

    # Get discussion group (must be pre-bound via /setdiscussion)
    discussion_id = get_discussion_chat_id()
    if not discussion_id:
        # Fallback: reveal in main group (and tell admin how to bind)
        await bot.send_message(
            MAIN_GROUP_ID,
            "ℹ️ No discussion group set. Revealing here.\n"
            "Admins: run /setdiscussion in the target group once to bind it."
        )
        discussion_id = MAIN_GROUP_ID

    if not replies:
        await bot.send_message(discussion_id, "No replies today. 😶")
        return

    await bot.send_message(
        discussion_id,
        "🔓 *Reveal time!* Here are today’s replies. Feel free to discuss until 17:00 tomorrow.",
        parse_mode="Markdown",
    )

    for uid, msg in replies.items():
        try:
            # Try to forward the original message (voice or text)
            await bot.forward_message(
                chat_id=discussion_id,
                from_chat_id=int(uid),
                message_id=msg["message_id"]
            )
        except Exception:
            # Fallback to attributed text if forward fails
            user = msg.get("from", {}).get("first_name", "Someone")
            text = msg.get("text")
            if text:
                await bot.send_message(
                    chat_id=discussion_id,
                    text=f"💬 *{user} said:* {text}",
                    parse_mode="Markdown"
                )

    # Invite participants (only if discussion group is not the main group)
    if discussion_id != MAIN_GROUP_ID:
        try:
            invite_link = await bot.create_chat_invite_link(chat_id=discussion_id)
            for uid in replies.keys():
                try:
                    await bot.send_message(
                        chat_id=int(uid),
                        text=f"🗣 The discussion is open! Join here:\n{invite_link.invite_link}"
                    )
                except Exception:
                    pass
        except Exception as e:
            print("Error creating invite link:", e)

    # Clear replies for next round
    save_json(REPLIES_FILE, {})

async def cleanup_discussion(context: CallbackContext):
    discussion_id = get_discussion_chat_id() or MAIN_GROUP_ID
    try:
        await context.bot.send_message(
            chat_id=discussion_id,
            text="🧹 Discussion closing — see you at 8 PM for a new one!"
        )
        # (Optional) Full message deletion would require tracking message_ids.
        # Keeping it simple per your request.
    except Exception:
        pass

# =========================
# 🕒 COMMAND: /nexttimes
# =========================
async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🕒 *Current schedule (Amsterdam time)*\n"
        f"• New prompt: {PROMPT_TIME.strftime('%H:%M')}\n"
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
        raise RuntimeError(
            "RENDER_EXTERNAL_URL is not set. On Render Web Services this is provided automatically."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nexttimes", show_schedule))
    app.add_handler(CommandHandler("setdiscussion", set_discussion))  # run inside the target discussion group

    # Only collect replies from private chats (text or voice)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.VOICE), collect_reply))

    # Jobs (daily)
    job_queue = app.job_queue
    job_queue.run_daily(send_daily_prompt,   time=PROMPT_TIME,   name="daily_prompt")
    job_queue.run_daily(last_hour_reminder,  time=REMINDER_TIME, name="reminder")
    job_queue.run_daily(reveal_replies,      time=REVEAL_TIME,   name="reveal")
    job_queue.run_daily(cleanup_discussion,  time=CLEANUP_TIME,  name="cleanup")

    # Webhook
    webhook_path = BOT_TOKEN  # secret-ish path
    webhook_url = f"{RENDER_URL.rstrip('/')}/{webhook_path}"
    print(f"Starting webhook on port {PORT}, webhook URL: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=webhook_path,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
