import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT_DIR / "hr_monitor" / "alerted_items.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Max age (hours) of a feed item to still be considered for alerting.
MAX_ITEM_AGE_HOURS = float(os.environ.get("HR_MONITOR_MAX_AGE_HOURS", "12"))
