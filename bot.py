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

# --- Daily Schedule (editable for testing) ---
# Set these to your test or real times (Amsterdam tz)
PROMPT_TIME   = time(14, 0, tzinfo=TIMEZONE)
REMINDER_TIME = time(14, 5, tzinfo=TIMEZONE)
REVEAL_TIME   = time(14, 15, tzinfo=TIMEZONE)
CLEANUP_TIME  = time(14, 20, tzinfo=TIMEZONE)

# =========================
# 📋 PROMPTS
# =========================

PROMPTS = [
    {"topic": "Mental Wellbeing", "text": "What’s one small thing that secretly keeps you sane when life gets messy?"},
    {"topic": "Fun Memories", "text": "What’s a memory with this group that instantly makes you grin?"},
    {"topic": "Future Plans", "text": "If this group planned a trip together, where would we end up — and who’s getting lost first?"},
]

# =========================
# 🗂️ FILES
# =========================

USED_PROMPTS_FILE = "used_prompts.json"
DISCUSSION_FILE   = "discussion_group.json"  # {"chat_id": int}
REPLIES_FILE      = "replies.json"           # {user_id: full_message_dict}
PARTICIPANTS_FILE = "participants.json"      # {"current": [user_ids], "last_invite_link": "...", "last_round": "YYYY-MM-DD"}

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

def set_participants(ids: list[int], invite_link: str | None, round_key: str):
    save_json(PARTICIPANTS_FILE, {
        "current": list(map(int, ids)),
        "last_invite_link": invite_link,
        "last_round": round_key,
    })

def get_participants():
    data = load_json(PARTICIPANTS_FILE)
    return {
        "current": [int(x) for x in data.get("current", [])],
        "last_invite_link": data.get("last_invite_link"),
        "last_round": data.get("last_round"),
    }

def today_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(TIMEZONE)
    return dt.strftime("%Y-%m-%d")

def next_datetime_at(t: time) -> datetime:
    """Return the next datetime (>= now) at local time 't'."""
    now = datetime.now(TIMEZONE)
    target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return target

# =========================
# 💬 HANDLERS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I’ll post a prompt in the group at the scheduled time. "
        "Reply to me *privately* (text or voice) before the reveal to join the discussion. 💬",
        parse_mode="Markdown"
    )

async def collect_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only accept private replies as entries
    if update.effective_chat.type != "private":
        return

    replies = load_json(REPLIES_FILE)
    user_id = str(update.message.from_user.id)
    replies[user_id] = update.message.to_dict()
    save_json(REPLIES_FILE, replies)

    # Track participant for this round
    p = get_participants()
    curr = set(p["current"])
    curr.add(int(user_id))
    set_participants(sorted(curr), p.get("last_invite_link"), today_key())

    await update.message.reply_text("Got it! Your reply’s saved for this round 💬")

async def set_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "Run this in the *discussion group* you want me to use.",
            parse_mode="Markdown"
        )
        return
    set_discussion_chat_id(chat.id)
    await update.message.reply_text("✅ This group is now set as the discussion space.")

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message in the MAIN group when someone joins."""
    chat = update.effective_chat
    if chat.id != MAIN_GROUP_ID:
        return
    bot_user = await context.bot.get_me()
    bot_link = f"https://t.me/{bot_user.username}"
    for user in update.message.new_chat_members:
        name = user.first_name or "there"
        await context.bot.send_message(
            chat_id=MAIN_GROUP_ID,
            text=(
                f"👋 Welcome, {name}!\n"
                f"To join the daily prompt and discussion, please open a DM with me first: {bot_link}\n"
                "Then just send your answer there before the reveal time. 🙌"
            )
        )

# =========================
# ⏰ SCHEDULED JOBS
# =========================

async def send_daily_prompt(context: CallbackContext):
    bot = context.bot
    prompt = get_daily_prompt()

    # Reset storage for new round
    save_json(REPLIES_FILE, {})
    set_participants([], None, today_key())

    # Unpin old prompt
    try:
        chat = await bot.get_chat(MAIN_GROUP_ID)
        if chat.pinned_message:
            await bot.unpin_chat_message(chat_id=MAIN_GROUP_ID)
    except Exception as e:
        print("Unpin error:", e)

    # Compose and pin new prompt
    text = (
        f"{prompt}\n\n"
        "📝 *How it works:*\n"
        "• Reply to me *in private* (text or voice).\n"
        f"• Reveal at *{REVEAL_TIME.strftime('%H:%M')}*.\n"
        f"• Discussion stays open until *{CLEANUP_TIME.strftime('%H:%M')}*.\n"
        "• Only people who replied will get a private invite link to the discussion. 💬"
    )
    msg = await bot.send_message(chat_id=MAIN_GROUP_ID, text=text, parse_mode="Markdown")
    try:
        await bot.pin_chat_message(chat_id=MAIN_GROUP_ID, message_id=msg.message_id)
    except Exception as e:
        print("Pin error:", e)

async def last_hour_reminder(context: CallbackContext):
    await context.bot.send_message(
        chat_id=MAIN_GROUP_ID,
        text=(
            "⏳ *Reminder:* Last minutes to reply privately before the reveal! "
            f"Reveal is at *{REVEAL_TIME.strftime('%H:%M')}*."
        ),
        parse_mode="Markdown"
    )

async def reveal_replies(context: CallbackContext):
    bot = context.bot
    replies = load_json(REPLIES_FILE)
    discussion_id = get_discussion_chat_id() or MAIN_GROUP_ID

    # Post a header
    await bot.send_message(
        chat_id=discussion_id,
        text=(
            "🔓 *Discussion open!* Here are today’s replies — feel free to react & comment. "
            f"Chat stays open until *{CLEANUP_TIME.strftime('%H:%M')}*."
        ),
        parse_mode="Markdown"
    )

    # Forward each reply (voice is forwarded; text is rendered)
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

    # Create a private invite link that expires at cleanup
    cleanup_dt = next_datetime_at(CLEANUP_TIME)
    expire_ts = int(cleanup_dt.timestamp())

    invite_link_obj = None
    try:
        invite_link_obj = await bot.create_chat_invite_link(
            chat_id=discussion_id,
            expire_date=expire_ts,
            member_limit=0  # unlimited until expiry
        )
    except Exception as e:
        print("Invite link error:", e)

    # DM the invite link only to today’s respondents
    p = get_participants()
    p_ids = p["current"]

    if invite_link_obj and p_ids:
        for uid in p_ids:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=(
                        "🗣 Your discussion link for today is ready!\n"
                        f"Join here: {invite_link_obj.invite_link}\n\n"
                        f"(Link expires at *{CLEANUP_TIME.strftime('%H:%M')}*.)"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"DM invite failed for {uid}: {e}")

        set_participants(p_ids, invite_link_obj.invite_link, today_key())

    # Clear replies after reveal; participants remain for cleanup
    save_json(REPLIES_FILE, {})

async def cleanup_discussion(context: CallbackContext):
    bot = context.bot
    discussion_id = get_discussion_chat_id() or MAIN_GROUP_ID
    p = get_participants()
    p_ids = p["current"]

    # Try to revoke last invite link so latecomers can't join
    if p.get("last_invite_link"):
        try:
            await bot.revoke_chat_invite_link(chat_id=discussion_id, invite_link=p["last_invite_link"])
        except Exception as e:
            print("Revoke link error:", e)

    # Politely close
    try:
        await bot.send_message(
            chat_id=discussion_id,
            text="🧹 Discussion closed — see you at the next prompt!"
        )
    except Exception:
        pass

    # Remove all participants of this round (so next reveal is exclusive again)
    for uid in p_ids:
        try:
            await bot.ban_chat_member(chat_id=discussion_id, user_id=uid)
            await bot.unban_chat_member(chat_id=discussion_id, user_id=uid)
        except Exception as e:
            print(f"Kick failed for {uid}: {e}")

    # Reset participants
    set_participants([], None, today_key())

# =========================
# 🕒 COMMAND: /nexttimes
# =========================
async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🕒 *Schedule (Amsterdam)*\n"
        f"• Prompt: {PROMPT_TIME.strftime('%H:%M')}\n"
        f"• Reminder: {REMINDER_TIME.strftime('%H:%M')}\n"
        f"• Reveal: {REVEAL_TIME.strftime('%H:%M')}\n"
        f"• Cleanup: {CLEANUP_TIME.strftime('%H:%M')}",
        parse_mode="Markdown"
    )

# =========================
# 🚀 MAIN (WEBHOOK on Render)
# =========================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nexttimes", show_schedule))
    app.add_handler(CommandHandler("setdiscussion", set_discussion))

    # Welcome new users in MAIN group
    app.add_handler(MessageHandler(filters.Chat(MAIN_GROUP_ID) & filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # Collect private replies (text or voice)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.VOICE), collect_reply))

    # Jobs
    jq = app.job_queue
    jq.run_daily(send_daily_prompt,  time=PROMPT_TIME,   name="daily_prompt")
    jq.run_daily(last_hour_reminder, time=REMINDER_TIME, name="reminder")
    jq.run_daily(reveal_replies,     time=REVEAL_TIME,   name="reveal")
    jq.run_daily(cleanup_discussion, time=CLEANUP_TIME,  name="cleanup")

    # ---- Webhook configuration for Render ----
    port = int(os.environ.get("PORT", "10000"))  # Render provides PORT
    base_url = os.environ.get("RENDER_EXTERNAL_URL")  # Render provides this public URL
    if not base_url:
        raise RuntimeError("Missing RENDER_EXTERNAL_URL. Ensure this is a Web Service on Render.")
    webhook_secret = os.environ.get("WEBHOOK_SECRET", "")  # optional but recommended

    # Use a unique path (bot token) to avoid collisions
    webhook_url = f"{base_url.rstrip('/')}/{BOT_TOKEN}"

    print(f"🚀 Starting webhook server on 0.0.0.0:{port}")
    print(f"🌐 Setting webhook to: {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,        # the path Telegram will call
        webhook_url=webhook_url,   # the full public URL
        secret_token=(webhook_secret or None),
        allowed_updates=Update.ALL_TYPES,
        # drop_pending_updates=True,  # uncomment if you want to discard old updates on restart
    )

if __name__ == "__main__":
    main()
