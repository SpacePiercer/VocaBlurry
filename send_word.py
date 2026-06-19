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

import scoring

# Data lives in a separate private repo in CI (checked out into VOCAB_DATA_DIR);
# falls back to the local ./data dir for local runs.
DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
VOCAB_FILE = DATA_DIR / "vocab.json"
DAILY_DIR = DATA_DIR / "daily"
WORDS_FILE = DATA_DIR / "review" / "words.json"
TZ = ZoneInfo("America/Vancouver")


def is_single_word(es: str) -> bool:
    """Reject multi-word phrases — only feed single Spanish words."""
    return len(es.split()) == 1


def learned_set() -> set[str]:
    """Normalized es of words already learned (score 5), to skip in the feed."""
    if not WORDS_FILE.exists():
        return set()
    words = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    return {
        w["es"].strip().casefold()
        for w in words
        if scoring.normalize(w)["learned"]
    }


def choose_entry(vocab: list[dict]) -> dict:
    """Pick a random single-word, not-yet-learned entry (falling back gracefully)."""
    learned = learned_set()
    eligible = [
        e for e in vocab
        if is_single_word(e["es"]) and e["es"].strip().casefold() not in learned
    ]
    if not eligible:  # everything single-word is learned — allow re-review
        eligible = [e for e in vocab if is_single_word(e["es"])] or vocab
    return random.choice(eligible)


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
    entry = choose_entry(vocab)
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
