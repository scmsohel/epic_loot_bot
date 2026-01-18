import os, json, time, threading, requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from telegram import (
    Bot, Update,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Dispatcher, CommandHandler,
    CallbackQueryHandler, CallbackContext
)

# ================= ENV =================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
CHANNEL_URL = os.getenv("CHANNEL_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN or not CHANNEL_USERNAME or not CHANNEL_URL or not ADMIN_ID:
    raise RuntimeError("Missing ENV values")

# ================= CONFIG =================
EPIC_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"

SUB_FILE = "subscribers.json"
USER_FILE = "all_users.json"
STATE_FILE = "last_state.json"

params = {
    "locale": "en-US",
    "country": "BD",
    "allowCountries": "BD"
}

BD_TZ = timezone(timedelta(hours=6))

# ================= JSON =================
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

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

# ================= TIME =================
def to_bd(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(BD_TZ)

def fmt(dt):
    return dt.strftime("%b %d, %I:%M %p")

def date_only(dt):
    return dt.strftime("%b %d")

# ================= EPIC =================
def fetch_epic():
    r = requests.get(EPIC_URL, params=params, timeout=20)
    items = r.json()["data"]["Catalog"]["searchStore"]["elements"]

    free_now, coming = [], []

    for g in items:
        promo = g.get("promotions")
        if not promo:
            continue

        title = g["title"]

        for p in promo.get("promotionalOffers", []):
            o = p["promotionalOffers"][0]
            if o["discountSetting"]["discountPercentage"] == 0:
                free_now.append({
                    "title": title,
                    "end": to_bd(o["endDate"])
                })

        for p in promo.get("upcomingPromotionalOffers", []):
            o = p["promotionalOffers"][0]
            coming.append({
                "title": title,
                "start": to_bd(o["startDate"]),
                "end": to_bd(o["endDate"])
            })

    coming.sort(key=lambda x: x["start"])
    return free_now, coming

# ================= CHANNEL =================
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

def join_warning(update, edit=False):
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
            join_warning(update)
            return
        return func(update, context)
    return wrapper

def is_admin(uid):
    return uid == ADMIN_ID

# ================= SUB =================
def sub_keyboard(chat_id):
    subs = load_set(SUB_FILE)
    if chat_id in subs:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔕 Unsubscribe", callback_data="UNSUB")]
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Subscribe", callback_data="SUB")]
    ])

# ================= COMMANDS =================
@guarded
def start(update: Update, context: CallbackContext):
    users = load_set(USER_FILE)
    users.add(update.message.chat_id)
    save_set(USER_FILE, users)

    update.message.reply_text(
        "👋 Welcome to *EpicLootBot* 🎮\n\n"
        "New FREE game unlock হলেই auto announce পাবে।",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

@guarded
def status(update: Update, context: CallbackContext):
    free_now, coming = fetch_epic()
    msg = ""

    if free_now:
        msg += "🎮 FREE GAMES NOW\n\n"
        for g in free_now:
            msg += f"• *{g['title']}*\n"
            msg += f"  ⏰ _Until {fmt(g['end'])}_\n\n"

    if coming:
        msg += "⏳ COMING SOON\n\n"
        for g in coming:
            msg += f"• *{g['title']}*\n"
            msg += f"  🗓 _{date_only(g['start'])} → {date_only(g['end'])}_\n\n"

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
        "🔕 Unsubscribed.",
        reply_markup=sub_keyboard(update.message.chat_id),
        parse_mode="Markdown"
    )

@guarded
def user_stats(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    users = load_set(USER_FILE)
    subs = load_set(SUB_FILE)
    update.message.reply_text(
        f"👥 *USER STATS*\n\n"
        f"Total: *{len(users)}*\n"
        f"Subscribed: *{len(subs)}*\n"
        f"Unsubscribed: *{len(users - subs)}*",
        parse_mode="Markdown"
    )

@guarded
def broadcast(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        update.message.reply_text("Usage:\n/broadcast message")
        return

    msg = "📢 *ADMIN NOTICE*\n\n" + " ".join(context.args)
    users = load_set(USER_FILE)

    sent = 0
    for uid in users:
        try:
            context.bot.send_message(uid, msg, parse_mode="Markdown")
            sent += 1
        except:
            pass

    update.message.reply_text(f"✅ Sent to {sent} users.")

# ================= BUTTON =================
def button_handler(update: Update, context: CallbackContext):
    q = update.callback_query
    chat_id = q.message.chat_id

    if not is_joined(context.bot, q.from_user.id):
        q.answer("Join channel first!", show_alert=True)
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
            free_now, _ = fetch_epic()
            titles = [g["title"] for g in free_now]

            old = load_state()
            new = [t for t in titles if t not in old]

            if new:
                subs = load_set(SUB_FILE)
                for g in free_now:
                    if g["title"] in new:
                        msg = (
                            "🎉 *NEW FREE GAME UNLOCKED!*\n\n"
                            f"🎮 *{g['title']}*\n"
                            f"⏰ _Until {fmt(g['end'])}_"
                        )
                        for uid in subs:
                            try:
                                bot.send_message(uid, msg, parse_mode="Markdown")
                            except:
                                pass

                save_state(titles)

        except Exception as e:
            print("Auto announce error:", e)

        time.sleep(120)

# ================= START =================
def start_bot():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(bot, None, workers=1, use_context=True)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("subscribe", subscribe))
    dp.add_handler(CommandHandler("unsubscribe", unsubscribe))
    dp.add_handler(CommandHandler("user", user_stats))
    dp.add_handler(CommandHandler("broadcast", broadcast))
    dp.add_handler(CallbackQueryHandler(button_handler))

    threading.Thread(
        target=auto_announce,
        args=(bot,),
        daemon=True
    ).start()

    offset = 0
    while True:
        updates = bot.get_updates(offset=offset, timeout=30)
        for u in updates:
            dp.process_update(u)
            offset = u.update_id + 1

if __name__ == "__main__":
    start_bot()
