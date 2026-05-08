import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "mafia_bot.db").strip()

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN. Укажи переменную окружения BOT_TOKEN.")
