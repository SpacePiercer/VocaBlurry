"""Drain queued Telegram updates and update per-word quiz scoring.

Handles two update types in chronological order:
  - callback_query: taps on the 🤔 button -> log to data/review/forgotten.json,
    add the word to the quiz pool (data/review/words.json), and reset its score
    to 0 (scoring.record_dontknow).
  - poll_answer: quiz answers -> look the poll up in pending_polls.json and move
    the word's score ±1 (scoring.record_answer).

Serverless by design: updates queue inside Telegram and are read here via
getUpdates with a persisted offset, so no webhook/always-on listener is needed.
This must be the only getUpdates consumer for the bot, or updates will race.

Each word is logged/scored at most once per message (deduped on date+index), so
tapping the same button repeatedly never double-counts. On the first drain that
sees a tap, the 🤔 button is replaced with an inert ✅ as a "recorded" marker.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import scoring

# Data lives in a separate private repo in CI (checked out into VOCAB_DATA_DIR);
# falls back to the local ./data dir for local runs.
DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
DAILY_DIR = DATA_DIR / "daily"
FORGOTTEN_FILE = DATA_DIR / "review" / "forgotten.json"
WORDS_FILE = DATA_DIR / "review" / "words.json"
OFFSET_FILE = DATA_DIR / "state" / "offset.json"
PENDING_POLLS_FILE = DATA_DIR / "state" / "pending_polls.json"

DONE_DATA = "noop"  # callback_data of the inert ✅ button after a word is recorded
PENDING_TTL_DAYS = 7  # drop unanswered quiz polls older than this


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8"))["offset"])
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": offset}) + "\n", encoding="utf-8")


def load_forgotten() -> list[dict]:
    if FORGOTTEN_FILE.exists():
        return json.loads(FORGOTTEN_FILE.read_text(encoding="utf-8"))
    return []


def save_forgotten(items: list[dict]) -> None:
    FORGOTTEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    FORGOTTEN_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def norm(s: str) -> str:
    return (s or "").strip().casefold()


def load_words() -> list[dict]:
    if WORDS_FILE.exists():
        return json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    return []


def save_words(words: list[dict]) -> None:
    WORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORDS_FILE.write_text(
        json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def index_words(words: list[dict]) -> dict[str, dict]:
    """Normalize every pool word and return a {norm(es): record} lookup."""
    return {norm(w["es"]): scoring.normalize(w) for w in words}


def get_word(words: list[dict], by_es: dict[str, dict], es: str, en: str | None) -> dict:
    """Find the pool word for `es`, creating (and normalizing) it if missing."""
    rec = by_es.get(norm(es))
    if rec is None:
        rec = scoring.normalize({"es": es, "en": en})
        words.append(rec)
        by_es[norm(es)] = rec
    elif en and not rec.get("en"):
        rec["en"] = en
    return rec


def load_pending() -> dict:
    if PENDING_POLLS_FILE.exists():
        return json.loads(PENDING_POLLS_FILE.read_text(encoding="utf-8"))
    return {}


def save_pending(pending: dict) -> None:
    PENDING_POLLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_POLLS_FILE.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def prune_pending(pending: dict) -> None:
    """Drop quiz polls left unanswered longer than PENDING_TTL_DAYS (in place)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=PENDING_TTL_DAYS)
    for pid in [
        pid
        for pid, v in pending.items()
        if datetime.fromisoformat(v["ts"]) < cutoff
    ]:
        del pending[pid]


def parse_key(callback_data: str) -> tuple[str, int] | None:
    """'f:{date}:{idx}' -> (date, idx); anything else (e.g. 'noop') -> None."""
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "f":
        return None
    try:
        return parts[1], int(parts[2])
    except ValueError:
        return None


def resolve_entry(date: str, idx: int) -> dict | None:
    """Look up the daily-log entry a tapped button refers to."""
    path = DAILY_DIR / f"{date}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))[idx]
    except (IndexError, json.JSONDecodeError):
        return None


def disable_button(token: str, chat_id: int, message_id: int) -> None:
    """Replace the 🤔 button with an inert ✅ so the message shows it was recorded.
    Best-effort: editing old messages can fail, which is harmless."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/editMessageReplyMarkup",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": json.dumps(
                    {"inline_keyboard": [[{"text": "✅", "callback_data": DONE_DATA}]]}
                ),
            },
            timeout=30,
        )
    except requests.RequestException:
        pass


def answer_callback(token: str, query_id: str, text: str) -> None:
    """Best-effort toast ack. Late answers ('query is too old') are ignored."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            json={"callback_query_id": query_id, "text": text},
            timeout=30,
        )
    except requests.RequestException:
        pass


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    offset = load_offset()

    resp = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={
            "offset": offset,
            "timeout": 0,
            "allowed_updates": json.dumps(["callback_query", "poll_answer"]),
        },
        timeout=60,
    )
    if not resp.ok:
        print(f"getUpdates error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    updates = resp.json().get("result", [])
    if not updates:
        print("No new updates.")
        return

    items = load_forgotten()
    seen = {(r["date"], r.get("idx")) for r in items}
    words = load_words()
    by_es = index_words(words)  # also migrates legacy records in place
    pending = load_pending()
    logged = scored = 0

    # Process in update_id order so the running score is deterministic.
    for upd in sorted(updates, key=lambda u: u["update_id"]):
        cq = upd.get("callback_query")
        if cq:
            logged += handle_tap(token, cq, items, seen, words, by_es)
            continue
        pa = upd.get("poll_answer")
        if pa:
            scored += handle_answer(pa, by_es, pending)

    prune_pending(pending)
    if logged:
        save_forgotten(items)
    save_words(words)
    save_pending(pending)
    save_offset(max(u["update_id"] for u in updates) + 1)
    print(
        f"Processed {len(updates)} update(s); logged {logged} forgotten word(s), "
        f"scored {scored} quiz answer(s)."
    )


def handle_tap(token, cq, items, seen, words, by_es) -> int:
    """Process a 🤔 tap: log it (deduped), add/reset the pool word, lock button.
    Returns 1 if a new forgotten word was logged, else 0."""
    key = parse_key(cq.get("data", ""))
    if key is None:
        # Inert ✅ (or unknown) button — acknowledge quietly, log nothing.
        answer_callback(token, cq["id"], "")
        return 0

    date, idx = key
    entry = resolve_entry(date, idx)
    if entry is None:
        answer_callback(token, cq["id"], "Couldn't find that word \U0001f615")
        return 0

    new = 0
    if key not in seen and entry.get("es"):  # dedupe: count each message once
        items.append(
            {
                "date": date,
                "idx": idx,
                "es": entry.get("es"),
                "en": entry.get("en"),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        seen.add(key)
        new = 1
        # Add to / reset in the quiz pool: a 🤔 tap means "I don't know this".
        rec = get_word(words, by_es, entry["es"], entry.get("en"))
        scoring.record_dontknow(rec)

    # Lock the button to ✅ (retries on every tap until it succeeds), then ack.
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    if chat_id and message_id:
        disable_button(token, chat_id, message_id)
    answer_callback(token, cq["id"], "Marked for review \U0001f44d")
    return new


def handle_answer(pa: dict, by_es: dict[str, dict], pending: dict) -> int:
    """Score a quiz poll_answer against pending_polls and update the word's stats.
    Returns 1 if an answer was scored, else 0."""
    pid = pa.get("poll_id")
    opts = pa.get("option_ids") or []
    rec = pending.get(pid)
    if not rec or not opts:  # unknown poll, or a retracted vote
        return 0
    correct = len(opts) == 1 and opts[0] == rec["correct_option_id"]
    word = by_es.get(norm(rec["es"]))
    if word is not None:
        scoring.record_answer(word, correct)
    del pending[pid]
    return 1


if __name__ == "__main__":
    main()
