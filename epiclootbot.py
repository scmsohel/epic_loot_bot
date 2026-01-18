import os
import json
import requests
import threading
import time
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

# ================= HELPERS =================
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
        return json.load(f).get("titles", [])

def save_state(titles):
    with open(STATE_FILE, "w") as f:
        json.dump({
            "titles": titles,
            "time": datetime.now(BD_TZ).isoformat()
        }, f, indent=2)

def to_bd(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BD_TZ)

def fmt(dt):
    return dt.strftime("%b %d, %I:%M %p")

# ================= EPIC API =================
def fetch_free_games():
    r = requests.get(EPIC_URL, params=params, timeout=20)
    games = r.json()["data"]["Catalog"]["searchStore"]["elements"]

    free = []
    for g in games:
        promo = g.get("promotions")
        if not promo:
            continue
        for p in promo.get("promotionalOffers", []):
            offer = p["promotionalOffers"][0]
            if offer["discountSetting"]["discountPercentage"] == 0:
                free.append({
                    "title": g["title"],
                    "end": to_bd(offer["endDate"])
                })
    return free

def current_titles():
    return sorted([g["title"] for g in fetch_free_games()])

# ================= CHANGE DETECT =================
def detect_change():
    now_titles = current_titles()
    old_titles = load_state()

    if now_titles != old_titles:
        save_state(now_titles)
        return True, now_titles
    return False, now_titles

# ================= AUTO ANNOUNCE =================
def auto_announce(bot: Bot):
    while True:
        now = datetime.now(BD_TZ)

        # Only check around 10 PM
        if now.hour == 22 and now.minute < 5:
            changed, titles = detect_change()
            if changed and titles:
                msg = "🎉 *NEW FREE GAME ON EPIC GAMES!*\n\n"
                for t in titles:
                    msg += f"🎮 *{t}*\n"
                msg += "\n👉 Grab it now!"

                subs = load_set(SUB_FILE)
                for chat_id in subs:
                    try:
                        bot.send_message(chat_id, msg, parse_mode="Markdown")
                    except:
                        pass
        time.sleep(300)  # 5 min

# ================= JOIN CHECK =================
def is_joined(bot, user_id):
    try:
        m = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("✅ Verify", callback_data="VERIFY")]
    ])

def guarded(func):
    def wrap(update: Update, context: CallbackContext):
        if not is_joined(context.bot, update.effective_user.id):
            update.message.reply_text(
                "🚫 Please join our channel first.",
                reply_markup=join_keyboard(),
                parse_mode="Markdown"
            )
            return
        return func(update, context)
    return wrap

# ================= COMMANDS =================
@guarded
def start(update: Update, context: CallbackContext):
    users = load_set(ALL_USER_FILE)
    users.add(update.message.chat_id)
    save_set(ALL_USER_FILE, users)

    update.message.reply_text(
        "👋 Welcome to *EpicLootBot* 🎮",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

def status(update: Update, context: CallbackContext):
    games = fetch_free_games()
    msg = "🎮 *FREE GAMES NOW*\n\n"
    for g in games:
        msg += f"• *{g['title']}*\n⏰ _Until {fmt(g['end'])}_\n\n"
    update.message.reply_text(msg, parse_mode="Markdown")

def sub_keyboard(cid):
    subs = load_set(SUB_FILE)
    if cid in subs:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔕 Unsubscribe", callback_data="UNSUB")]])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Subscribe", callback_data="SUB")]])

def subscribe(update: Update, context: CallbackContext):
    subs = load_set(SUB_FILE)
    subs.add(update.message.chat_id)
    save_set(SUB_FILE, subs)
    update.message.reply_text("✅ Subscribed!", reply_markup=sub_keyboard(update.message.chat_id))

def unsubscribe(update: Update, context: CallbackContext):
    subs = load_set(SUB_FILE)
    subs.discard(update.message.chat_id)
    save_set(SUB_FILE, subs)
    update.message.reply_text("🔕 Unsubscribed.", reply_markup=sub_keyboard(update.message.chat_id))

def button_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    cid = q.message.chat_id
    subs = load_set(SUB_FILE)

    if q.data == "SUB":
        subs.add(cid)
        save_set(SUB_FILE, subs)
        q.answer("Subscribed")
    elif q.data == "UNSUB":
        subs.discard(cid)
        save_set(SUB_FILE, subs)
        q.answer("Unsubscribed")

    q.edit_message_reply_markup(reply_markup=sub_keyboard(cid))

# ================= DISPATCHER =================
def setup_dispatcher(bot):
    dp = Dispatcher(bot, None, workers=1, use_context=True)
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("subscribe", subscribe))
    dp.add_handler(CommandHandler("unsubscribe", unsubscribe))
    dp.add_handler(CallbackQueryHandler(button_handler))
    return dp

# ================= START BACKGROUND =================
def start_background(bot):
    t = threading.Thread(target=auto_announce, args=(bot,), daemon=True)
    t.start()
