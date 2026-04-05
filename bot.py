#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
import json
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiohttp import web

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TARGET_URL = "https://lynther.sytes.net/?p=lora&q=Loonie"
DEFAULT_MIN_DAYS = 25
CHECK_INTERVAL_HOURS = 6
CONFIG_FILE = "config.json"
# =============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or CHAT_ID == 0:
    raise ValueError("❌ Не заданы BOT_TOKEN или CHAT_ID в переменных окружения!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"min_days": DEFAULT_MIN_DAYS}


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


bot_state = load_config()

def find_inactive_loonies(url: str, min_days: int = 25) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    lines = soup.get_text().split("\n")

    id_pattern = re.compile(r"#️⃣\s*(\d+)")
    days_pattern = re.compile(r"🕸️\s*(\d+)\s*days?")
    loonie_pattern = re.compile(r"\bLoonie\b", re.IGNORECASE)

    current = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue

        id_match = id_pattern.search(line)
        if id_match:
            if current.get("id") and current.get("days") is not None and current.get("has_loonie"):
                if current["days"] > min_days:
                    results.append({
                        "id": current["id"],
                        "days": current["days"],
                        "name": current.get("name", "Loonie")
                    })
            current = {
                "id": id_match.group(1),
                "days": None,
                "has_loonie": bool(loonie_pattern.search(line)),
                "name": "Loonie"
            }
            continue

        if current.get("id"):
            days_match = days_pattern.search(line)
            if days_match:
                current["days"] = int(days_match.group(1))

            if loonie_pattern.search(line):
                current["has_loonie"] = True
    if current.get("id") and current.get("days") is not None and current.get("has_loonie"):
        if current["days"] > min_days:
            results.append({
                "id": current["id"],
                "days": current["days"],
                "name": current.get("name", "Loonie")
            })

    return results


def format_msg(lora: dict) -> str:
    return (
        f"🧠 <b>{lora['name']}</b>\n"
        f"🆔 <code>ID: {lora['id']}</code>\n"
        f"🕸️ <b>{lora['days']} дней</b> без использования\n"
        f"🗑️ <code>/dellora {lora['id']}</code>\n"
        f"{'─' * 30}"
    )


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я мониторю лоры с тегом <b>Loonie</b>.\n\n"
        "Команды:\n"
        "🔍 <code>/check</code> — проверить сайт вручную\n"
        "📊 <code>/status</code> — текущие настройки\n"
        "⚙️ <code>/setdays &lt;N&gt;</code> — изменить порог дней",
        parse_mode="HTML"
    )


@dp.message(Command("check"))
async def cmd_check(message: Message):
    await message.answer("🔍 Сканирую сайт...")
    loras = find_inactive_loonies(TARGET_URL, bot_state["min_days"])
    if not loras:
        await message.answer("✅ Лоры с текущим порогом не найдены.")
        return
    for l in loras:
        await message.answer(format_msg(l), parse_mode="HTML")
        await asyncio.sleep(0.3)


@dp.message(Command("setdays"))
async def cmd_setdays(message: Message):
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():        await message.answer(
            "⚠️ Используй: <code>/setdays &lt;число&gt;</code>\nПример: <code>/setdays 30</code>",
            parse_mode="HTML"
        )
        return

    new_days = int(parts[1])
    if new_days < 1:
        await message.answer("⚠️ Число должно быть больше 0")
        return

    bot_state["min_days"] = new_days
    save_config({"min_days": new_days})
    await message.answer(
        f"✅ Порог изменён на <b>{new_days} дней</b>. Все следующие проверки будут использовать это значение.",
        parse_mode="HTML"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    await message.answer(
        f"⚙️ <b>Настройки бота:</b>\n"
        f"🌐 Сайт: <code>{TARGET_URL}</code>\n"
        f"🕸️ Текущий порог: <b>{bot_state['min_days']} дней</b>\n"
        f"🔄 Автопроверка: каждые {CHECK_INTERVAL_HOURS} ч.",
        parse_mode="HTML"
    )


async def periodic_check():
    await asyncio.sleep(60)
    while True:
        try:
            loras = find_inactive_loonies(TARGET_URL, bot_state["min_days"])
            if loras:
                for l in loras:
                    await bot.send_message(chat_id=CHAT_ID, text=format_msg(l), parse_mode="HTML")
                    await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Ошибка периодической проверки: {e}")
        await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600)


async def on_startup():
    logger.info(f"🚀 Бот запущен! Порог: {bot_state['min_days']} дней")
    asyncio.create_task(periodic_check())


async def health_handler(request):    return web.Response(text="OK")


async def run_web_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8080")))
    await site.start()
    logger.info(f"🌐 Health server on port {os.getenv('PORT', '8080')}")


async def main():
    dp.startup.register(on_startup)
    await asyncio.gather(dp.start_polling(bot), run_web_server())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен.")
