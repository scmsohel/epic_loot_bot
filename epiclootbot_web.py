import os
from flask import Flask, request
from telegram import Bot, Update
import epiclootbot

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "epiclootbot")

bot = Bot(token=BOT_TOKEN)
dispatcher = epiclootbot.setup_dispatcher(bot)

app = Flask(__name__)

@app.route("/")
def home():
    return "EpicLootBot webhook is running"

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
