"""End-of-day quiz: send one Telegram quiz poll per word that appeared
today, with wrong options drawn from the whole vocabulary."""
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

OPTION_LIMIT = 100  # Telegram poll option max length
QUESTION_LIMIT = 300  # Telegram poll question max length
NUM_OPTIONS = 4


def send_quiz(token: str, chat_id: str, es: str, correct: str, pool: list[str]) -> bool:
    distractors = [t for t in pool if t.casefold() != correct.casefold()]
    random.shuffle(distractors)
    # dedupe distractors case-insensitively, keep up to NUM_OPTIONS - 1
    chosen, seen = [], {correct.casefold()}
    for d in distractors:
        if d.casefold() not in seen:
            seen.add(d.casefold())
            chosen.append(d)
        if len(chosen) == NUM_OPTIONS - 1:
            break

    options = [correct] + chosen
    random.shuffle(options)
    options = [o[:OPTION_LIMIT] for o in options]
    correct_id = options.index(correct[:OPTION_LIMIT])

    question = f"What does “{es}” mean?"[:QUESTION_LIMIT]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendPoll",
        json={
            "chat_id": chat_id,
            "question": question,
            "options": json.dumps(options, ensure_ascii=False),
            "type": "quiz",
            "correct_option_id": correct_id,
            "is_anonymous": False,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Poll error for {es!r}: {resp.status_code} {resp.text}", file=sys.stderr)
        return False
    return True


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    date = datetime.now(TZ).date().isoformat()
    path = DAILY_DIR / f"{date}.json"
    if not path.exists():
        print(f"No words logged for {date}; nothing to quiz.")
        return
    day = json.loads(path.read_text(encoding="utf-8"))

    # distinct words sent today (preserve order)
    todays = []
    seen = set()
    for e in day:
        if e["es"].casefold() not in seen and e.get("en"):
            seen.add(e["es"].casefold())
            todays.append(e)
    if not todays:
        print(f"No quizzable words for {date}.")
        return

    pool = [e["en"] for e in json.loads(VOCAB_FILE.read_text(encoding="utf-8")) if e.get("en")]

    ok = True
    for e in todays:
        if not send_quiz(token, chat_id, e["es"], e["en"], pool):
            ok = False
    print(f"Sent {len(todays)} quiz poll(s) for {date}.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
