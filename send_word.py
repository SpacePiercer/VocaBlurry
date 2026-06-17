"""Send one random Spanish word to Telegram with its English translation
blurred (tap-to-reveal spoiler), and log the word to today's daily file."""
import html
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Data lives in a separate private repo in CI (checked out into VOCAB_DATA_DIR);
# falls back to the local ./data dir for local runs.
DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
VOCAB_FILE = DATA_DIR / "vocab.json"
DAILY_DIR = DATA_DIR / "daily"
TZ = ZoneInfo("America/Vancouver")


def log_daily(entry: dict) -> tuple[str, int]:
    """Append the sent entry to data/daily/{Vancouver-date}.json.

    Returns (date, index) where index is this entry's position in the day's list,
    used to build the inline button's callback_data.
    """
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(TZ).date().isoformat()
    path = DAILY_DIR / f"{date}.json"
    day = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    day.append(entry)
    path.write_text(
        json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return date, len(day) - 1


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    vocab = json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
    entry = random.choice(vocab)
    es, en = entry["es"], entry["en"]

    # Log first so we know this entry's (date, index) for the button callback_data.
    date, idx = log_daily(entry)

    text = (
        f"\U0001f1ea\U0001f1f8 {html.escape(es)}\n"
        f"\U0001f1ec\U0001f1e7 <tg-spoiler>{html.escape(en)}</tg-spoiler>"
    )
    # Single emoji-only "didn't remember" button (🤔). Text-free so it always fits
    # regardless of message width; its meaning lives in the bot's profile
    # description. The blurred translation above is unchanged.
    reply_markup = {
        "inline_keyboard": [[{"text": "\U0001f914", "callback_data": f"f:{date}:{idx}"}]]
    }

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": json.dumps(reply_markup),
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Telegram API error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    print(f"Sent: {es} -> {en}")


if __name__ == "__main__":
    main()
