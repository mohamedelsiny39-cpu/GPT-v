import os
import threading

from server import app as flask_app
from bot import build_bot_app, BOT_TOKEN


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def main():
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if not BOT_TOKEN:
        print("⚠️  متغير BOT_TOKEN مش متظبط، السيرفر هيفضل شغال بس البوت لأ.")
        flask_thread.join()
        return

    bot_app = build_bot_app()
    print("✅ السيرفر والبوت شغالين...")
    bot_app.run_polling()


if __name__ == "__main__":
    main()
