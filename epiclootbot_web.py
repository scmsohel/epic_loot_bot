import threading
from flask import Flask
import epiclootbot

app = Flask(__name__)
bot_started = False

@app.route("/")
def home():
    return "EpicLootBot is running"

def run_bot_once():
    global bot_started
    if not bot_started:
        bot_started = True
        epiclootbot.main()

if __name__ == "__main__":
    threading.Thread(target=run_bot_once, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
