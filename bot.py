import os
import json
import random
import asyncio
from datetime import time, datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackContext
)
from pytz import timezone

# =========================
# Environment Variables
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
MAIN_GROUP_ID = int(os.environ["GROUP_ID"])  # Main chat group
TIMEZONE = timezone("Europe/Amsterdam")

# =========================
# Prompts Section
# =========================
PROMPTS = [
    {"topic": "Mental Wellbeing", "text": "What’s one small thing that secretly keeps you sane when life gets messy?"},
    {"topic": "Mental Wellbeing", "text": "When was the last time you took a proper break — like really unplugged — and what did you do?"},
    {"topic": "Mental Wellbeing", "text": "What’s something you’ve started doing lately that makes your days feel lighter?"},
    {"topic": "Mental Wellbeing", "text": "If you could press pause on everything for a day, what would you spend that day doing?"},
    {"topic": "Mental Wellbeing", "text": "Be honest — what’s your brain’s current “weather forecast”? (sunny, foggy, thunderstorms…)"},
    {"topic": "Mental Wellbeing", "text": "What’s a habit you dropped that you kinda want back?"},
    {"topic": "Mental Wellbeing", "text": "When do you usually feel most like yourself?"},
    {"topic": "Mental Wellbeing", "text": "What’s something you wish more people understood about you right now?"},

    {"topic": "Fun Memories", "text": "What’s a memory with this group that instantly makes you grin?"},
    {"topic": "Fun Memories", "text": "Who in this group is most likely to turn a normal night into a story we’ll tell for years?"},
    {"topic": "Fun Memories", "text": "What’s the dumbest inside joke you still remember?"},
    {"topic": "Fun Memories", "text": "If you could relive one hilarious moment from our past together, which would it be?"},
    {"topic": "Fun Memories", "text": "What’s something funny that happened recently that you wish we’d all been there for?"},
    {"topic": "Fun Memories", "text": "What’s a trip, party, or random day that didn’t go as planned but turned out even better?"},
    {"topic": "Fun Memories", "text": "What’s a “you had to be there” moment that still cracks you up?"},
    {"topic": "Fun Memories", "text": "What’s one memory you’d 100% put in a highlight reel of your life?"},

    {"topic": "Future Plans", "text": "If this group planned a trip together, where would we end up — and who’s getting lost first?"},
    {"topic": "Future Plans", "text": "What’s one dream you secretly hope you’ll pull off (even if it sounds crazy)?"},
    {"topic": "Future Plans", "text": "If we met again in 10 years, what do you hope your life looks like?"},
    {"topic": "Future Plans", "text": "What’s a skill or hobby you’ve been “meaning to start” forever — be honest!"},
    {"topic": "Future Plans", "text": "If you had to make one bold change in your life before next summer, what would it be?"},
    {"topic": "Future Plans", "text": "If your future self could send you a short voice note, what do you think they’d say?"},
    {"topic": "Future Plans", "text": "What’s something you’d do if you knew you couldn’t fail?"},
    {"topic": "Future Plans", "text": "What’s a goal that scares you a little (in a good way)?"},

    {"topic": "Friendship & Growth", "text": "What’s something you’ve learned from someone in this group?"},
    {"topic": "Friendship & Growth", "text": "When did you first realize this group had become your people?"},
    {"topic": "Friendship & Growth", "text": "What’s one thing you wish we did more often together?"},
    {"topic": "Friendship & Growth", "text": "How do you think you’ve changed the most since we first met?"},
    {"topic": "Friendship & Growth", "text": "If you could tell your past self one thing from what you’ve learned lately, what would it be?"},
    {"topic": "Friendship & Growth", "text": "What’s one way you try to show up for your friends, even on off days?"}
]

USED_PROMPTS_FILE = "used_prompts.json"
DISCUSSION_FILE = "discussion_group.json"
REPLIES_FILE = "replies.json"

# =========================
# Utility Functions
# =========================
def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(file, data):
    with open(file, "w") as f:
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
    return f"🌞 **Daily Prompt**\n🧭 *Topic:* {chosen['topic']}\n💬 *Prompt:* {chosen['text']}"

# =========================
# Handlers
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hey there! I’ll send you a daily question at 8 PM. Reply here privately to join the next reveal!")

async def collect_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    replies = load_json(REPLIES_FILE)
    user_id = str(update.message.from_user.id)
    replies[user_id] = update.message.to_dict()
    save_json(REPLIES_FILE, replies)
    await update.message.reply_text("Got it! Your reply’s in for today’s round 💬")

# =========================
# Scheduled Jobs
# =========================
async def send_daily_prompt(context: CallbackContext):
    prompt = get_daily_prompt()
    await context.bot.send_message(chat_id=MAIN_GROUP_ID, text=prompt, parse_mode="Markdown")

async def reveal_replies(context: CallbackContext):
    replies = load_json(REPLIES_FILE)
    bot = context.bot

    # Get or create discussion group
    discussion_info = load_json(DISCUSSION_FILE)
    if "chat_id" not in discussion_info:
        chat = await bot.create_chat(title="Daily Discussion", users=[])
        discussion_info["chat_id"] = chat.id
        save_json(DISCUSSION_FILE, discussion_info)
    group_id = discussion_info["chat_id"]

    # Clear old messages
    try:
        await bot.delete_message(chat_id=group_id, message_id=0)
    except Exception:
        pass

    # Forward all replies
    for uid, msg in replies.items():
        try:
            if "voice" in msg:
                await bot.forward_message(chat_id=group_id, from_chat_id=uid, message_id=msg["message_id"])
            elif "text" in msg:
                user = msg["from"]["first_name"]
                await bot.send_message(chat_id=group_id, text=f"💬 *{user} said:* {msg['text']}", parse_mode="Markdown")
        except Exception as e:
            print("Error forwarding:", e)

    # Invite participants
    invite_link = await bot.create_chat_invite_link(chat_id=group_id, member_limit=0, creates_join_request=False)
    for uid in replies.keys():
        try:
            await bot.send_message(chat_id=uid, text=f"🗣 Discussion is live! Join here:\n{invite_link.invite_link}")
        except Exception:
            pass

    save_json(REPLIES_FILE, {})  # clear replies

async def cleanup_discussion(context: CallbackContext):
    info = load_json(DISCUSSION_FILE)
    if "chat_id" in info:
        try:
            await context.bot.delete_chat_messages(chat_id=info["chat_id"])
        except Exception:
            pass

# =========================
# Main
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.VOICE, collect_reply))

    job_queue = app.job_queue

    job_queue.run_daily(send_daily_prompt, time=time(20, 0, tzinfo=TIMEZONE), name="daily_prompt")
    job_queue.run_daily(reveal_replies, time=time(18, 0, tzinfo=TIMEZONE), name="reveal")
    job_queue.run_daily(cleanup_discussion, time=time(17, 0, tzinfo=TIMEZONE), name="cleanup")

    app.run_polling()

if __name__ == "__main__":
    main()
