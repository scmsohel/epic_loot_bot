import os
import json
import time
import threading
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
    raise RuntimeError("BOT_TOKEN missing")
if not CHANNEL_USERNAME or not CHANNEL_URL:
    raise RuntimeError("CHANNEL config missing")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID missing")

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

# ================= JSON HELPERS =================
def load_set(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        return set(json.load(f))

def save_set(path, data):
    with open(path, "w") as f:
        json.dump(list(data), f)

def load_state():
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(titles):
    with open(STATE_FILE, "w") as f:
        json.dump(titles, f)

# ================= TIME =================
def to_bd(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BD_TZ)

def fmt(dt):
    return dt.strftime("%b %d, %I:%M %p")

def date_only(dt):
    return dt.strftime("%b %d")

# ================= EPIC FETCH =================
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
            coming_soon.append({
                "title": title,
                "start": to_bd(offer["startDate"]),
                "end": to_bd(offer["endDate"])
            })

    coming_soon.sort(key=lambda x: x["start"])
    return free_now, coming_soon

# ================= CHANNEL CHECK =================
def is_joined(bot, user_id):
    try:
        m = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return m.status in ("member", "administrator", "creator")
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
        "Please join our channel to use this bot."
    )
    if edit and update.callback_query:
        update.callback_query.edit_message_text(
            text, reply_markup=join_keyboard(), parse_mode="Markdown"
        )
    else:
        update.message.reply_text(
            text, reply_markup=join_keyboard(), parse_mode="Markdown"
        )

# ================= GUARD =================
def guarded(func):
    def wrapper(update: Update, context: CallbackContext):
        if not is_joined(context.bot, update.effective_user.id):
            send_join_warning(update, context)
            return
        return func(update, context)
    return wrapper

def is_admin(user_id):
    return user_id == ADMIN_ID

# ================= SUBSCRIBE =================
def sub_keyboard(chat_id):
    subs = load_set(SUB_FILE)
    if chat_id in subs:
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔕 Unsubscribe", callback_data="UNSUB")]]
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔔 Subscribe", callback_data="SUB")]]
    )

# ================= COMMANDS =================
@guarded
def start(update: Update, context: CallbackContext):
    users = load_set(ALL_USER_FILE)
    users.add(update.message.chat_id)
    save_set(ALL_USER_FILE, users)

    update.message.reply_text(
        "👋 Welcome to *EpicLootBot* 🎮\n\n"
        "New FREE games unlock হলে auto alert পাবে।",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

@guarded
def status(update: Update, context: CallbackContext):
    free_now, coming_soon = fetch_epic_data()
    msg = ""

    if free_now:
        msg += "🎮 FREE GAMES NOW\n"
        for g in free_now:
            msg += f"\n• *{g['title']}*\n"
            msg += f"  ⏰ _Free now — until {fmt(g['end'])}_\n"

    if coming_soon:
        msg += "\n⏳ COMING SOON\n"
        for g in coming_soon:
            msg += f"\n• *{g['title']}*\n"
            msg += f"  🗓 _Free {date_only(g['start'])} → {date_only(g['end'])}_\n"

    update.message.reply_text(msg.strip(), parse_mode="Markdown")

@guarded
def subscribe(update: Update, context: CallbackContext):
    subs = load_set(SUB_FILE)
    subs.add(update.message.chat_id)
    save_set(SUB_FILE, subs)
    update.message.reply_text(
        "✅ Subscribed! Auto announce পাবে।",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

@guarded
def unsubscribe(update: Update, context: CallbackContext):
    subs = load_set(SUB_FILE)
    subs.discard(update.message.chat_id)
    save_set(SUB_FILE, subs)
    update.message.reply_text(
        "🔕 Unsubscribed. আর alert যাবে না।",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

# ================= ADMIN =================
@guarded
def user_stats(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return

    all_users = load_set(ALL_USER_FILE)
    subs = load_set(SUB_FILE)

    msg = (
        "👥 *USER STATS*\n\n"
        f"• Total Users: *{len(all_users)}*\n"
        f"• Subscribed Users: *{len(subs)}*\n"
        f"• Unsubscribed Users: *{len(all_users - subs)}*"
    )
    update.message.reply_text(msg, parse_mode="Markdown")

@guarded
def broadcast(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        update.message.reply_text("Usage:\n/broadcast your message")
        return

    message = "📢 *ADMIN NOTICE*\n\n" + " ".join(context.args)
    users = load_set(ALL_USER_FILE)

    sent = 0
    for uid in users:
        try:
            context.bot.send_message(uid, message, parse_mode="Markdown")
            sent += 1
        except:
            pass

    update.message.reply_text(f"✅ Broadcast sent to {sent} users.")

# ================= BUTTON =================
def button_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    chat_id = q.message.chat_id

    if not is_joined(context.bot, q.from_user.id):
        q.answer("Join channel first", show_alert=True)
        q.edit_message_reply_markup(reply_markup=join_keyboard())
        return

    subs = load_set(SUB_FILE)

    if q.data == "SUB":
        subs.add(chat_id)
        q.answer("Subscribed ✅")
    elif q.data == "UNSUB":
        subs.discard(chat_id)
        q.answer("Unsubscribed 🔕")
    elif q.data == "VERIFY_JOIN":
        q.answer("Verified ✅")

    save_set(SUB_FILE, subs)
    q.edit_message_reply_markup(reply_markup=sub_keyboard(chat_id))

# ================= AUTO ANNOUNCE =================
def auto_announce(bot: Bot):
    while True:
        try:
            free_now, _ = fetch_epic_data()
            titles = [g["title"] for g in free_now]

            old_titles = load_state()
            new_titles = [t for t in titles if t not in old_titles]

            if new_titles:
                subs = load_set(SUB_FILE)

                for g in free_now:
                    if g["title"] in new_titles:
                        msg = (
                            "🎉 *NEW FREE GAME UNLOCKED!*\n\n"
                            f"🎮 *{g['title']}*\n"
                            f"⏰ _Free now — until {fmt(g['end'])}_"
                        )
                        for uid in subs:
                            try:
                                bot.send_message(uid, msg, parse_mode="Markdown")
                            except:
                                pass

                save_state(titles)

        except Exception as e:
            print("Auto announce error:", e)

        time.sleep(90)

# ================= DISPATCHER =================
def setup_dispatcher(bot):
    dp = Dispatcher(bot, None, workers=1, use_context=True)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("subscribe", subscribe))
    dp.add_handler(CommandHandler("unsubscribe", unsubscribe))
    dp.add_handler(CommandHandler("user", user_stats))
    dp.add_handler(CommandHandler("broadcast", broadcast))
    dp.add_handler(CallbackQueryHandler(button_handler))

    return dp

# ================= START =================
def start_bot():
    bot = Bot(BOT_TOKEN)
    dp = setup_dispatcher(bot)

    threading.Thread(target=auto_announce, args=(bot,), daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    start_bot()
