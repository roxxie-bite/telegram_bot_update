import os
import json
import requests
import time
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from telegram import Bot, Update, BotCommand
from telegram.ext import Updater, CommandHandler, CallbackContext

os.system("pip uninstall -y telegram python-telegram-bot")
os.system("pip install telegram python-telegram-bot==13.15")
os.system("python bot.py")

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OWNER_ID = os.getenv("OWNER_ID")
INTERVAL_FILE = "interval.txt"
LAST_CHECK_FILE = "last_check.json"
SOURCES_FILE = "sources.json"

# === KEEP-ALIVE ===
app = Flask("")


@app.route("/")
def home():
    return "Бот работает!"


def run():
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    Thread(target=run).start()


# === УТИЛИТЫ ===
def get_interval_minutes():
    try:
        with open(INTERVAL_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return 15


def load_sources():
    with open(SOURCES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_last_check():
    if os.path.exists(LAST_CHECK_FILE):
        with open(LAST_CHECK_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_last_check(data):
    with open(LAST_CHECK_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# === ПРОВЕРКА ИСТОЧНИКОВ ===
def check_all_sources(bot: Bot = None) -> list:
    last_data = load_last_check()
    sources = load_sources()
    results = []

    for source in sources:
        original_name = source.get("name")  # имя из sources.json, ключ для last_check
        url = source.get("url")
        parsed_name = original_name  # пока совпадает

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Парсим дату обновления
            tag = soup.find('div', class_='updatedAtDate')
            current_update_line = tag.text.strip() if tag else None

            # Парсим настоящее название из <div class="flx Fonkartochka"><h1>...</h1>
            name_block = soup.find('div', class_='flx Fonkartochka')
            h1 = name_block.find('h1') if name_block else None
            parsed_name = h1.text.strip() if h1 else original_name

        except Exception as e:
            error_msg = f"❌ [{original_name}] Ошибка:\n{str(e)}\n{url}"
            print(error_msg)
            if bot:
                bot.send_message(chat_id=CHAT_ID, text=error_msg)
            continue

        if not current_update_line:
            msg = f"⚠️ [{parsed_name}] Не найдена дата обновления:\n{url}"
            print(msg)
            if bot:
                bot.send_message(chat_id=CHAT_ID, text=msg)
            continue

        saved_line = last_data.get(original_name)

        if saved_line != current_update_line:
            print(f"[{parsed_name}] Обновление найдено.")
            message = (f"🔔 Обновление: *{parsed_name}*\n"
                       f"`{current_update_line}`\n"
                       f"[Перейти на страницу]({url})")
            if bot:
                bot.send_message(chat_id=CHAT_ID,
                                 text=message,
                                 parse_mode='Markdown')
            last_data[original_name] = current_update_line
            results.append((parsed_name, True))
        else:
            print(f"[{parsed_name}] Без изменений.")
            results.append((parsed_name, False))

    save_last_check(last_data)
    return results


# === КОМАНДЫ ===
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "✅ Бот запущен.\n"
        "Команды:\n"
        "/check — проверить обновления\n"
        "/setinterval <мин> — изменить интервал (только для владельца)")


def manual_check(update: Update, context: CallbackContext):
    update.message.reply_text("🔍 Проверяю все источники...")
    results = check_all_sources(context.bot)

    updated = [name for name, changed in results if changed]
    if updated:
        update.message.reply_text(
            f"✅ Обновления найдены: {', '.join(updated)}")
    elif results:
        update.message.reply_text("ℹ️ Обновлений не найдено.")
    else:
        update.message.reply_text("⚠️ Не удалось проверить источники.")


def set_interval(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    if user_id != OWNER_ID:
        update.message.reply_text("🚫 У тебя нет прав изменять интервал.")
        return

    try:
        minutes = int(context.args[0])
        if minutes < 1 or minutes > 1440:
            raise ValueError
        with open(INTERVAL_FILE, 'w') as f:
            f.write(str(minutes))
        update.message.reply_text(
            f"✅ Интервал проверки установлен: {minutes} минут.")
    except:
        update.message.reply_text("⚠️ Использование: /setinterval <минут>")


# === АВТО-ПРОВЕРКА ===
def auto_check(bot: Bot):
    while True:
        check_all_sources(bot)
        time.sleep(get_interval_minutes() * 60)


# === ЗАПУСК ===
def main():
    keep_alive()
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    updater.bot.set_my_commands([
        BotCommand("start", "Старт и справка"),
        BotCommand("check", "Проверить обновления"),
        BotCommand("setinterval", "Изменить интервал (только для владельца)")
    ])

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("check", manual_check))
    dp.add_handler(CommandHandler("setinterval", set_interval))

    Thread(target=auto_check, args=(updater.bot, ), daemon=True).start()
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
