"""Write public, aggregates-only learning stats to stats.json in this (public) repo.

Read by the portfolio site's live widget. Publishes counts and a date only:
no words, no per-answer logs, no times of day.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import scoring

DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
WORDS_FILE = DATA_DIR / "review" / "words.json"
OUT_FILE = Path(__file__).parent / "stats.json"


def compute(words: list[dict], today: str) -> dict:
    words = [scoring.normalize(dict(w)) for w in words]
    review = [w for w in words if w["in_review"]]
    avg = sum(w["score"] for w in review) / len(review) if review else 0
    return {
        "date": today,
        "learned": sum(w["learned"] for w in words),
        "in_review": len(review),
        "avg_score": round(avg, 1),
    }


def main() -> None:
    words = json.loads(WORDS_FILE.read_text(encoding="utf-8")) if WORDS_FILE.exists() else []
    stats = compute(words, datetime.now(timezone.utc).date().isoformat())
    OUT_FILE.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"stats.json: {stats}")


if __name__ == "__main__":
    main()
