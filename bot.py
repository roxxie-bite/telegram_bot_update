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

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TARGET_URL = "https://lynther.sytes.net/?p=lora&q=Loonie"
DEFAULT_MIN_DAYS = 25
CHECK_INTERVAL_HOURS = 6
CONFIG_FILE = "config.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or CHAT_ID == 0:
    raise ValueError("Missing BOT_TOKEN or CHAT_ID")

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

def find_inactive_loonies(url, min_days):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        logger.error("Request error: " + str(e))        return []

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

def format_msg(lora):    parts = []
    parts.append("🧠 <b>" + str(lora["name"]) + "</b>")
    parts.append("🆔 <code>ID: " + str(lora["id"]) + "</code>")
    parts.append("🕸️ <b>" + str(lora["days"]) + " дней</b> без использования")
    parts.append("🗑️ <code>/dellora " + str(lora["id"]) + "</code>")
    parts.append("─" * 30)
    return "\n".join(parts)
