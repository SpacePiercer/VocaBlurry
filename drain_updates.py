"""Drain queued Telegram callback_query updates (taps on the 🤔 button) and log
the corresponding words to data/review/forgotten.json.

Serverless by design: button taps queue inside Telegram and are read here via
getUpdates with a persisted offset, so no webhook/always-on listener is needed.
This must be the only getUpdates consumer for the bot, or updates will race.

Each word is logged at most once per message (deduped on date+index), so tapping
the same button repeatedly never produces duplicates. On the first drain that
sees a tap, the 🤔 button is replaced with an inert ✅ as a "recorded" marker.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

# Data lives in a separate private repo in CI (checked out into VOCAB_DATA_DIR);
# falls back to the local ./data dir for local runs.
DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
DAILY_DIR = DATA_DIR / "daily"
FORGOTTEN_FILE = DATA_DIR / "review" / "forgotten.json"
OFFSET_FILE = DATA_DIR / "state" / "offset.json"

DONE_DATA = "noop"  # callback_data of the inert ✅ button after a word is recorded


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
            "allowed_updates": json.dumps(["callback_query"]),
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
    logged = 0

    for upd in updates:
        cq = upd.get("callback_query")
        if not cq:
            continue
        key = parse_key(cq.get("data", ""))
        if key is None:
            # Inert ✅ (or unknown) button — acknowledge quietly, log nothing.
            answer_callback(token, cq["id"], "")
            continue

        date, idx = key
        entry = resolve_entry(date, idx)
        if entry is None:
            answer_callback(token, cq["id"], "Couldn't find that word \U0001f615")
            continue

        if key not in seen:  # dedupe: log each message at most once
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
            logged += 1

        # Lock the button to ✅ (retries on every tap until it succeeds), then ack.
        msg = cq.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id and message_id:
            disable_button(token, chat_id, message_id)
        answer_callback(token, cq["id"], "Marked for review \U0001f44d")

    if logged:
        save_forgotten(items)
    save_offset(max(u["update_id"] for u in updates) + 1)
    print(f"Processed {len(updates)} update(s); logged {logged} new forgotten word(s).")


if __name__ == "__main__":
    main()
