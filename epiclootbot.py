import os
import json
import requests
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from telegram import (
    Bot,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    Dispatcher,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext
)


# ================= ENV =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_URL = os.getenv("CHANNEL_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not found in .env")
if not CHANNEL_USERNAME or not CHANNEL_URL:
    raise RuntimeError("❌ CHANNEL_USERNAME or CHANNEL_URL not found in .env")
if not ADMIN_ID:
    raise RuntimeError("❌ ADMIN_ID not found in .env")

# ================= CONFIG =================
EPIC_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
SUB_FILE = "subscribers.json"
STATE_FILE = "last_state.json"
ALL_USER_FILE = "all_users.json"

params = {
    "locale": "en-US",
    "country": "BD",
    "allowCountries": "BD"
}

BD_TZ = timezone(timedelta(hours=6))
# ========================================


# ---------- TIME HELPERS ----------
def to_bd(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BD_TZ)

def fmt(dt):
    return dt.strftime("%b %d, %I:%M %p")

def date_only(dt):
    return dt.strftime("%b %d")


# ---------- JSON STORAGE ----------
def load_json(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        return set(json.load(f))

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(list(data), f)


# ---------- CHANNEL CHECK ----------
def is_joined(bot, user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False


def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Verify", callback_data="VERIFY_JOIN")]
    ])


def send_join_warning(update, context, edit=False):
    text = (
        "🚫 *Access Restricted*\n\n"
        "You are not joined this channel.\n"
        "Please join to use this bot."
    )

    if edit and update.callback_query:
        update.callback_query.edit_message_text(
            text,
            reply_markup=join_keyboard(),
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text(
            text,
            reply_markup=join_keyboard(),
            parse_mode="Markdown"
        )


# ---------- SUBSCRIBE BUTTON ----------
def sub_keyboard(chat_id):
    subs = load_json(SUB_FILE)
    if chat_id in subs:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔕 Unsubscribe", callback_data="UNSUB")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔔 Subscribe", callback_data="SUB")]
        ])


# ---------- USER TRACK ----------
def track_user(chat_id):
    users = load_json(ALL_USER_FILE)
    users.add(chat_id)
    save_json(ALL_USER_FILE, users)


# ---------- EPIC DATA ----------
def fetch_epic_data():
    r = requests.get(EPIC_URL, params=params, timeout=20)
    games = r.json()["data"]["Catalog"]["searchStore"]["elements"]

    free_now, coming_soon = [], []

    for g in games:
        promo = g.get("promotions")
        if not promo:
            continue

        title = g["title"]

        for p in promo.get("promotionalOffers", []):
            offer = p["promotionalOffers"][0]
            if offer["discountSetting"]["discountPercentage"] == 0:
                free_now.append({
                    "title": title,
                    "end": to_bd(offer["endDate"])
                })

        for p in promo.get("upcomingPromotionalOffers", []):
            offer = p["promotionalOffers"][0]
            start = to_bd(offer["startDate"])
            end = to_bd(offer["endDate"])
            if "mystery" not in title.lower():
                coming_soon.append({
                    "title": title,
                    "start": start,
                    "end": end
                })

    coming_soon.sort(key=lambda x: x["start"])
    return free_now, coming_soon


# ---------- MESSAGE ----------
def build_status():
    free_now, coming_soon = fetch_epic_data()
    msg = ""

    if free_now:
        msg += "🎮 FREE GAMES NOW\n"
        for g in free_now:
            msg += f"• *{g['title']}*\n"
            msg += f"  ⏰ Free now — until _{fmt(g['end'])}_\n"
        msg += "\n"

    if coming_soon:
        msg += "⏳ COMING SOON\n"
        for g in coming_soon:
            msg += f"• *{g['title']}*\n"
            msg += f"  🗓 Free _{date_only(g['start'])} → {date_only(g['end'])}_\n\n"

    return msg.strip()


# ---------- COMMAND GUARD ----------
def guarded(func):
    def wrapper(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        if not is_joined(context.bot, user_id):
            send_join_warning(update, context)
            return
        return func(update, context)
    return wrapper


# ---------- COMMANDS ----------
@guarded
def start(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    track_user(chat_id)
    update.message.reply_text(
        "👋 Welcome to *EpicLootBot* 🎮\n\n"
        "You can now use the bot features below.",
        reply_markup=sub_keyboard(chat_id),
        parse_mode="Markdown"
    )


@guarded
def status(update: Update, context: CallbackContext):
    track_user(update.message.chat_id)
    update.message.reply_text(build_status(), parse_mode="Markdown")


@guarded
def subscribe(update: Update, context: CallbackContext):
    track_user(update.message.chat_id)
    subs = load_json(SUB_FILE)
    subs.add(update.message.chat_id)
    save_json(SUB_FILE, subs)
    update.message.reply_text(
        "✅ Subscribed!",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )


@guarded
def unsubscribe(update: Update, context: CallbackContext):
    track_user(update.message.chat_id)
    subs = load_json(SUB_FILE)
    subs.discard(update.message.chat_id)
    save_json(SUB_FILE, subs)
    update.message.reply_text(
        "🔕 Unsubscribed.",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )


# ---------- ADMIN COMMANDS ----------
def admin_only(update: Update):
    return update.effective_user.id == ADMIN_ID


def total_user(update: Update, context: CallbackContext):
    if not admin_only(update):
        return
    users = load_json(ALL_USER_FILE)
    update.message.reply_text(
        f"📊 *Bot Users*\n\n👥 Total Users: *{len(users)}*",
        parse_mode="Markdown"
    )


def sub_user(update: Update, context: CallbackContext):
    if not admin_only(update):
        return
    subs = load_json(SUB_FILE)
    update.message.reply_text(
        f"✅ *Subscribed Users*\n\n👥 Total: *{len(subs)}*",
        parse_mode="Markdown"
    )


def unsub_user(update: Update, context: CallbackContext):
    if not admin_only(update):
        return
    users = load_json(ALL_USER_FILE)
    subs = load_json(SUB_FILE)
    update.message.reply_text(
        f"🔕 *Unsubscribed Users*\n\n"
        f"👥 Total: *{len(users - subs)}*",
        parse_mode="Markdown"
    )


# ---------- BUTTON HANDLER ----------
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == "VERIFY_JOIN":
        if is_joined(context.bot, user_id):
            query.edit_message_text(
                "✅ Verification successful!\n\nYou can now use the bot.",
                parse_mode="Markdown"
            )
        else:
            send_join_warning(update, context, edit=True)

    elif query.data in ("SUB", "UNSUB"):
        if not is_joined(context.bot, user_id):
            send_join_warning(update, context, edit=True)
            return

        subs = load_json(SUB_FILE)
        chat_id = query.message.chat_id
        track_user(chat_id)

        if query.data == "SUB":
            subs.add(chat_id)
            query.answer("Subscribed ✅")
        else:
            subs.discard(chat_id)
            query.answer("Unsubscribed 🔕")

        save_json(SUB_FILE, subs)
        query.edit_message_reply_markup(reply_markup=sub_keyboard(chat_id))


# ---------- MAIN ----------
def setup_dispatcher(bot):
    dp = Dispatcher(bot, None, workers=0, use_context=True)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("subscribe", subscribe))
    dp.add_handler(CommandHandler("unsubscribe", unsubscribe))

    dp.add_handler(CommandHandler("total_user", total_user))
    dp.add_handler(CommandHandler("sub_user", sub_user))
    dp.add_handler(CommandHandler("unsub_user", unsub_user))

    dp.add_handler(CallbackQueryHandler(button_handler))
    return dp


if __name__ == "__main__":
    main()
