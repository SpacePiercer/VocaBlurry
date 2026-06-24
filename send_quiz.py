"""Nightly quiz over your "problematic" words (the ones you flagged with 🤔).

Picks a weighted sample (favoring words you get wrong most) without replacement,
capped at MAX_QUIZ, and sends one native quiz poll per word. Each poll's id and
correct option are recorded to pending_polls.json so the drain can score your
answers later (poll_answer) and update per-word progress in words.json.
"""
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

import scoring

# Data lives in a separate private repo in CI (checked out into VOCAB_DATA_DIR);
# falls back to the local ./data dir for local runs.
DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
VOCAB_FILE = DATA_DIR / "vocab.json"
WORDS_FILE = DATA_DIR / "review" / "words.json"
FORGOTTEN_FILE = DATA_DIR / "review" / "forgotten.json"
PENDING_POLLS_FILE = DATA_DIR / "state" / "pending_polls.json"

OPTION_LIMIT = 100  # Telegram poll option max length
QUESTION_LIMIT = 300  # Telegram poll question max length
NUM_OPTIONS = 4
MAX_QUIZ = 8  # max words quizzed per night (your 5-10 range)


def load_words() -> list[dict]:
    if WORDS_FILE.exists():
        return json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    return []


def save_words(words: list[dict]) -> None:
    WORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORDS_FILE.write_text(
        json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def seed_from_forgotten(words: list[dict]) -> bool:
    """Add any 🤔-tapped words missing from words.json. Returns True if changed."""
    if not FORGOTTEN_FILE.exists():
        return False
    forgotten = json.loads(FORGOTTEN_FILE.read_text(encoding="utf-8"))
    have = {scoring.norm(w["es"]) for w in words}
    changed = False
    for e in forgotten:
        if e.get("es") and e.get("en") and scoring.norm(e["es"]) not in have:
            words.append(scoring.normalize({"es": e["es"], "en": e["en"]}))
            have.add(scoring.norm(e["es"]))
            changed = True
    return changed


def weighted_sample(words: list[dict], k: int) -> list[dict]:
    """Sample up to k distinct words without replacement; weight favors words with
    more incorrect and fewer correct answers: (incorrect + 1) / (correct + 1)."""
    items = list(words)
    weights = [(w.get("incorrect", 0) + 1) / (w.get("correct", 0) + 1) for w in items]
    chosen = []
    for _ in range(min(k, len(items))):
        total = sum(weights)
        r = random.uniform(0, total)
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if r <= acc:
                chosen.append(items.pop(i))
                weights.pop(i)
                break
    return chosen


def send_quiz(token: str, chat_id: str, es: str, correct: str, pool: list[str]):
    """Send one quiz poll. Returns (poll_id, correct_option_id) or None on failure."""
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
            "options": options,
            "type": "quiz",
            "correct_option_id": correct_id,
            "is_anonymous": False,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"Poll error for {es!r}: {resp.status_code} {resp.text}", file=sys.stderr)
        return None
    return resp.json()["result"]["poll"]["id"], correct_id


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    words = load_words()
    added = seed_from_forgotten(words)
    for w in words:  # migrate legacy records + ensure scoring fields
        scoring.normalize(w)

    active = [w for w in words if not w["learned"] and w.get("en")]
    if not active:
        if added:
            print(f"Seeded {sum(1 for w in words if not w.get('quizzes'))} new word(s) from forgotten log.")
        print("No words in review; nothing to quiz.")
        save_words(words)  # persist any migration
        return

    selected = weighted_sample(active, MAX_QUIZ)
    pool = [
        e["en"]
        for e in json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
        if e.get("en")
    ]

    pending = (
        json.loads(PENDING_POLLS_FILE.read_text(encoding="utf-8"))
        if PENDING_POLLS_FILE.exists()
        else {}
    )
    sent, ok = 0, True
    for w in selected:
        result = send_quiz(token, chat_id, w["es"], w["en"], pool)
        if result is None:
            ok = False
            continue
        poll_id, correct_id = result
        pending[poll_id] = {
            "es": w["es"],
            "en": w["en"],
            "correct_option_id": correct_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        scoring.record_quiz_sent(w)  # count this appearance in a quiz
        sent += 1

    save_words(words)
    PENDING_POLLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_POLLS_FILE.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Sent {sent} quiz poll(s) from {len(active)} word(s) in review.")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
