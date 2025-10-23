# bot.py
import os
import json
import random
import logging
from datetime import time, datetime, timedelta
from typing import Optional

from pytz import timezone
from telegram import Update, ChatInviteLink
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, Application, CommandHandler, MessageHandler,
    ContextTypes, CallbackContext, filters
)

# =========================
# 🔧 CONFIGURATION
# =========================

BOT_TOKEN   = os.environ["BOT_TOKEN"]
MAIN_GROUP_ID = int(os.environ["GROUP_ID"])
PUBLIC_URL  = os.environ["PUBLIC_URL"].rstrip("/")  # e.g., https://ripple-bot.onrender.com
PORT        = int(os.environ.get("PORT", "10000"))  # Render injects PORT

# Timezone
TZ = timezone("Europe/Amsterdam")

# --- Daily Schedule (EDIT THESE FOR TESTING OR PROD) ---
# For testing in the same day, just set these to times later today.
PROMPT_TIME   = time(15, 30, tzinfo=TZ)   # 20:00 – post the daily prompt
REMINDER_TIME = time(15, 35, tzinfo=TZ)   # 17:00 – reminder (1h before reveal by default)
REVEAL_TIME   = time(15, 40, tzinfo=TZ)   # 18:00 – open discussion & DM invite links
CLEANUP_TIME  = time(15, 55, tzinfo=TZ)   # 17:00 next day – close & remove participants

# Files for lightweight persistence (Render’s disk is ephemeral across restarts, okay for tests)
USED_PROMPTS_FILE = "used_prompts.json"          # {"used": [indices]}
DISCUSSION_FILE   = "discussion_group.json"      # {"chat_id": <int>}
REPLIES_FILE      = "replies.json"               # {"<user_id>": <message_dict>}
PARTICIPANTS_FILE = "participants.json"          # {"current":[ids], "last_invite_link":"...", "last_round":"YYYY-MM-DD"}

# =========================
# 🗒️ PROMPTS (no repeats until all are used)
# =========================

PROMPTS = [
    # 🧘 Mental Wellbeing
    {"topic": "Mental Wellbeing", "text": "What’s one small thing that secretly keeps you sane when life gets messy?"},
    {"topic": "Mental Wellbeing", "text": "When was the last time you took a proper break — like really unplugged — and what did you do?"},
    {"topic": "Mental Wellbeing", "text": "What’s something you’ve started doing lately that makes your days feel lighter?"},
    {"topic": "Mental Wellbeing", "text": "If you could press pause on everything for a day, what would you spend that day doing?"},
    {"topic": "Mental Wellbeing", "text": "Be honest — what’s your brain’s current “weather forecast”? (sunny, foggy, thunderstorms…)"},
    {"topic": "Mental Wellbeing", "text": "What’s a habit you dropped that you kinda want back?"},
    {"topic": "Mental Wellbeing", "text": "When do you usually feel most like yourself?"},
    {"topic": "Mental Wellbeing", "text": "What’s something you wish more people understood about you right now?"},

    # 🎉 Fun Memories
    {"topic": "Fun Memories", "text": "What’s a memory with this group that instantly makes you grin?"},
    {"topic": "Fun Memories", "text": "Who in this group is most likely to turn a normal night into a story we’ll tell for years?"},
    {"topic": "Fun Memories", "text": "What’s the dumbest inside joke you still remember?"},
    {"topic": "Fun Memories", "text": "If you could relive one hilarious moment from our past together, which would it be?"},
    {"topic": "Fun Memories", "text": "What’s something funny that happened recently that you wish we’d all been there for?"},
    {"topic": "Fun Memories", "text": "What’s a trip, party, or random day that didn’t go as planned but turned out even better?"},
    {"topic": "Fun Memories", "text": "What’s a “you had to be there” moment that still cracks you up?"},
    {"topic": "Fun Memories", "text": "What’s one memory you’d 100% put in a highlight reel of your life?"},

    # 🚀 Future Plans
    {"topic": "Future Plans", "text": "If this group planned a trip together, where would we end up — and who’s getting lost first?"},
    {"topic": "Future Plans", "text": "What’s one dream you secretly hope you’ll pull off (even if it sounds crazy)?"},
    {"topic": "Future Plans", "text": "If we met again in 10 years, what do you hope your life looks like?"},
    {"topic": "Future Plans", "text": "What’s a skill or hobby you’ve been “meaning to start” forever — be honest!"},
    {"topic": "Future Plans", "text": "If you had to make one bold change in your life before next summer, what would it be?"},
    {"topic": "Future Plans", "text": "If your future self could send you a short voice note, what do you think they’d say?"},
    {"topic": "Future Plans", "text": "What’s something you’d do if you knew you couldn’t fail?"},
    {"topic": "Future Plans", "text": "What’s a goal that scares you a little (in a good way)?"},

    # 💫 Friendship & Growth
    {"topic": "Friendship & Growth", "text": "What’s something you’ve learned from someone in this group?"},
    {"topic": "Friendship & Growth", "text": "When did you first realize this group had become your people?"},
    {"topic": "Friendship & Growth", "text": "What’s one thing you wish we did more often together?"},
    {"topic": "Friendship & Growth", "text": "How do you think you’ve changed the most since we first met?"},
    {"topic": "Friendship & Growth", "text": "If you could tell your past self one thing from what you’ve learned lately, what would it be?"},
    {"topic": "Friendship & Growth", "text": "What’s one way you try to show up for your friends, even on off days?"},
]

# =========================
# 🧰 UTILITIES
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def load_json(path: str):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def today_key(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(TZ)
    return dt.strftime("%Y-%m-%d")

def next_dt_at(t: time) -> datetime:
    now = datetime.now(TZ)
    target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if target < now:
        target += timedelta(days=1)
    return target

def get_discussion_chat_id() -> Optional[int]:
    data = load_json(DISCUSSION_FILE)
    cid = data.get("chat_id")
    return int(cid) if cid is not None else None

def set_discussion_chat_id(chat_id: int):
    save_json(DISCUSSION_FILE, {"chat_id": int(chat_id)})

def get_participants():
    data = load_json(PARTICIPANTS_FILE)
    return {
        "current": [int(x) for x in data.get("current", [])],
        "last_invite_link": data.get("last_invite_link"),
        "last_round": data.get("last_round"),
    }

def set_participants(ids: list[int], invite_link: Optional[str], round_key: str):
    save_json(PARTICIPANTS_FILE, {
        "current": [int(x) for x in ids],
        "last_invite_link": invite_link,
        "last_round": round_key
    })

def get_daily_prompt_text() -> str:
    used = load_json(USED_PROMPTS_FILE).get("used", [])
    if len(used) >= len(PROMPTS):
        used = []
    choices = [i for i in range(len(PROMPTS)) if i not in used]
    idx = random.choice(choices)
    used.append(idx)
    save_json(USED_PROMPTS_FILE, {"used": used})
    p = PROMPTS[idx]
    return f"🌞 *Daily Prompt*\n🧭 *Topic:* {p['topic']}\n💬 *Prompt:* {p['text']}"

def fmt_hhmm(t: time) -> str:
    return t.strftime("%H:%M")

# =========================
# 💬 HANDLERS
# =========================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply in DMs or group with basic instructions."""
    bot = await context.bot.get_me()
    bot_link = f"https://t.me/{bot.username}"
    text = (
        "Hey! I’ll post a daily prompt in the main group.\n\n"
        "• Reply to me *privately* (text or voice/audio) to participate.\n"
        f"• Reveal is at *{fmt_hhmm(REVEAL_TIME)}*.\n"
        f"• The discussion stays open until *{fmt_hhmm(CLEANUP_TIME)}*.\n\n"
        f"If you haven’t yet, open a DM with me here: {bot_link}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def welcome_new_in_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message when *main* group gets a new member."""
    if update.effective_chat.id != MAIN_GROUP_ID:
        return
    bot = await context.bot.get_me()
    bot_link = f"https://t.me/{bot.username}"
    for user in update.message.new_chat_members:
        name = user.first_name or "there"
        await context.bot.send_message(
            chat_id=MAIN_GROUP_ID,
            text=(f"👋 Welcome, {name}!\n"
                  f"To join the daily prompt, please DM the bot first: {bot_link}\n"
                  f"Then send your answer there before *{fmt_hhmm(REVEAL_TIME)}*."),
            parse_mode=ParseMode.MARKDOWN
        )

async def welcome_in_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tiny welcome if someone joins the discussion group (optional nicety)."""
    disc_id = get_discussion_chat_id()
    if disc_id and update.effective_chat.id == disc_id:
        for user in update.message.new_chat_members:
            await context.bot.send_message(
                chat_id=disc_id,
                text=(f"👋 Welcome, {user.first_name or 'friend'}! "
                      f"Today’s chat stays open until *{fmt_hhmm(CLEANUP_TIME)}*. Enjoy!"),
                parse_mode=ParseMode.MARKDOWN
            )

async def collect_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect replies only from private chat (text, voice, audio)."""
    if update.effective_chat.type != "private":
        return

    # Save full message dict so we can forward it exactly
    replies = load_json(REPLIES_FILE)
    uid = str(update.message.from_user.id)
    replies[uid] = update.message.to_dict()
    save_json(REPLIES_FILE, replies)

    # Track participant for THIS round
    p = get_participants()
    current = set(p["current"])
    current.add(int(uid))
    set_participants(sorted(current), p.get("last_invite_link"), today_key())

    await update.message.reply_text("Got it! Your reply’s saved for this round 💬")

async def cmd_setdiscussion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run this *inside the discussion group* once. It marks that chat as the discussion room."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "Run /setdiscussion *inside the discussion group* you want me to use.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    set_discussion_chat_id(chat.id)
    await update.message.reply_text("✅ This chat is now set as the discussion space.")

# =========================
# ⏰ SCHEDULED JOBS
# =========================

async def job_send_prompt(context: CallbackContext):
    """Post the prompt in main group, reset round storage, and pin."""
    bot = context.bot

    # Reset state for a new round
    save_json(REPLIES_FILE, {})
    set_participants([], None, today_key())

    # Unpin old prompt if any
    try:
        chat = await bot.get_chat(MAIN_GROUP_ID)
        if chat.pinned_message:
            await bot.unpin_chat_message(MAIN_GROUP_ID)
    except Exception as e:
        logging.info(f"No old pin to unpin or error: {e}")

    prompt = get_daily_prompt_text()
    text = (
        f"{prompt}\n\n"
        "📝 *How it works:*\n"
        "• Reply to me *in private* (text or voice/audio).\n"
        f"• Reveal at *{fmt_hhmm(REVEAL_TIME)}*.\n"
        f"• Discussion stays open until *{fmt_hhmm(CLEANUP_TIME)}*.\n"
        "• Only people who replied will receive a private invite link. 💬"
    )
    msg = await bot.send_message(chat_id=MAIN_GROUP_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    try:
        await bot.pin_chat_message(chat_id=MAIN_GROUP_ID, message_id=msg.message_id)
    except Exception as e:
        logging.warning(f"Pin error: {e}")

async def job_reminder(context: CallbackContext):
    await context.bot.send_message(
        chat_id=MAIN_GROUP_ID,
        text=(f"⏳ *Reminder:* last minutes to reply privately before reveal at "
              f"*{fmt_hhmm(REVEAL_TIME)}*."),
        parse_mode=ParseMode.MARKDOWN
    )

async def job_reveal(context: CallbackContext):
    """Forward replies into discussion, DM invite link to today’s participants."""
    bot = context.bot
    replies = load_json(REPLIES_FILE)

    disc_id = get_discussion_chat_id()
    if not disc_id:
        # Safety fallback: use MAIN_GROUP if discussion group not configured
        disc_id = MAIN_GROUP_ID
        logging.warning("Discussion group not set. Using MAIN_GROUP_ID as discussion room.")

    # Open the room
    await bot.send_message(
        chat_id=disc_id,
        text=(f"🔓 *Discussion open!* Here are today’s replies — react & comment.\n"
              f"Chat stays open until *{fmt_hhmm(CLEANUP_TIME)}*."),
        parse_mode=ParseMode.MARKDOWN
    )

    # Forward every reply (text, voice/audio) by original message_id
    for uid, msg in replies.items():
        try:
            await bot.forward_message(
                chat_id=disc_id,
                from_chat_id=int(uid),
                message_id=msg["message_id"]
            )
        except Exception as e:
            # Fallback: attributed text if forwarding fails
            user = msg.get("from", {}).get("first_name", "Someone")
            text = msg.get("text")
            if text:
                await bot.send_message(
                    chat_id=disc_id,
                    text=f"💬 *{user} said:* {text}",
                    parse_mode=ParseMode.MARKDOWN
                )
            logging.info(f"Forward failed for {uid}: {e}")

    # Create a one-time invite link that expires at cleanup
    cleanup_dt = next_dt_at(CLEANUP_TIME)
    expire_ts = int(cleanup_dt.timestamp())
    invite_obj: Optional[ChatInviteLink] = None

    try:
        invite_obj = await bot.create_chat_invite_link(
            chat_id=disc_id,
            expire_date=expire_ts,
            member_limit=0  # unlimited until expiry
        )
    except Exception as e:
        logging.error(f"Invite link creation failed. Is the bot admin with 'Invite Users'? Error: {e}")

    # DM the link to today’s participants only
    p = get_participants()
    same_round = (p["last_round"] == today_key())
    ids = p["current"] if same_round else []

    if not ids:
        logging.info("No participants recorded for this round to DM.")
    elif not invite_obj:
        logging.error("Invite link missing; cannot DM participants.")
    else:
        for uid in ids:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=(f"🗣 Your discussion link for today is ready!\n"
                          f"Join here: {invite_obj.invite_link}\n\n"
                          f"(Link expires at *{fmt_hhmm(CLEANUP_TIME)}*.)"),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                # User may not accept DMs or never pressed Start (shouldn’t happen if they replied)
                logging.info(f"DM invite failed for {uid}: {e}")

        # Persist for cleanup
        set_participants(ids, invite_obj.invite_link, today_key())

    # Clear replies after reveal (participants remain until cleanup)
    save_json(REPLIES_FILE, {})

async def job_cleanup(context: CallbackContext):
    """Close the discussion and remove participants who joined for this round."""
    bot = context.bot
    disc_id = get_discussion_chat_id() or MAIN_GROUP_ID
    p = get_participants()
    ids = p["current"]

    # Revoke last invite link
    if p.get("last_invite_link"):
        try:
            await bot.revoke_chat_invite_link(chat_id=disc_id, invite_link=p["last_invite_link"])
        except Exception as e:
            logging.info(f"Revoke failed (maybe already expired): {e}")

    # Closing message
    try:
        await bot.send_message(chat_id=disc_id, text="🧹 Discussion closed — see you at the next prompt!")
    except Exception:
        pass

    # Remove participants (requires admin with 'Ban Users')
    for uid in ids:
        try:
            await bot.ban_chat_member(chat_id=disc_id, user_id=uid)
            await bot.unban_chat_member(chat_id=disc_id, user_id=uid)  # quick unban => kick without ban
        except Exception as e:
            logging.info(f"Kick failed for {uid}: {e}")

    # Reset participant list
    set_participants([], None, today_key())

# =========================
# 🕒 COMMAND: /nexttimes
# =========================

async def cmd_nexttimes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🕒 *Schedule (Amsterdam)*\n"
        f"• Prompt: {fmt_hhmm(PROMPT_TIME)}\n"
        f"• Reminder: {fmt_hhmm(REMINDER_TIME)}\n"
        f"• Reveal: {fmt_hhmm(REVEAL_TIME)}\n"
        f"• Cleanup: {fmt_hhmm(CLEANUP_TIME)}",
        parse_mode=ParseMode.MARKDOWN
    )

# =========================
# 🌐 WEBHOOK BOOTSTRAP
# =========================

def build_app() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("nexttimes", cmd_nexttimes))
    app.add_handler(CommandHandler("setdiscussion", cmd_setdiscussion))

    # Welcome messages
    app.add_handler(MessageHandler(filters.Chat(MAIN_GROUP_ID) & filters.StatusUpdate.NEW_CHAT_MEMBERS,
                                   welcome_new_in_main))
    # Optional pleasant welcome in discussion room
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_in_discussion))

    # Collect replies in private (text, voice notes, audio files)
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.TEXT | filters.VOICE | filters.AUDIO),
            collect_reply
        )
    )

    # Jobs (PTB’s JobQueue runs with the application)
    jq = app.job_queue
    jq.run_daily(job_send_prompt,   time=PROMPT_TIME,   name="daily_prompt")
    jq.run_daily(job_reminder,      time=REMINDER_TIME, name="reminder")
    jq.run_daily(job_reveal,        time=REVEAL_TIME,   name="reveal")
    jq.run_daily(job_cleanup,       time=CLEANUP_TIME,  name="cleanup")

    return app

def main():
    app = build_app()

    # Use token in the URL path (simple/secure enough for hobby projects).
    url_path = BOT_TOKEN
    webhook_url = f"{PUBLIC_URL}/{url_path}"

    # Run webhook server (Tornado) and set webhook at Telegram
    # Render will see the bound $PORT and be happy ✅
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=url_path,
        webhook_url=webhook_url,
    )

if __name__ == "__main__":
    main()
