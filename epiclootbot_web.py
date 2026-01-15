import threading
from flask import Flask

# তোমার আসল bot code এখান থেকে import হবে
import epiclootbot

app = Flask(__name__)

@app.route("/")
def home():
    return "EpicLootBot is running on Render"

def run_bot():
    epiclootbot.main()

if __name__ == "__main__":
    # Telegram bot background thread
    threading.Thread(target=run_bot, daemon=True).start()

    # Render requires a web server
    app.run(host="0.0.0.0", port=10000)

