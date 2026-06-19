"""Per-word quiz scoring for the 🤔-flagged word pool (data/review/words.json).

A pool word carries a running `score` in [0, 5], updated as quiz answers and 🤔
taps are processed in chronological order:

  correct quiz answer   -> score + 1   (capped at 5)
  incorrect quiz answer -> score - 1   (floored at 0)
  🤔 "don't know" tap    -> score reset to 0

`learned` and `in_review` are derived from the score, not stored independently:
a word is `learned` while score == 5 and `in_review` while it's in the pool
(`drained`) but not yet learned. So a 🤔 tap on a learned word resets it to 0 and
puts it back in review. `learned` replaces the old `retired` flag, which is
migrated on read. `drained` is True for every pool word (a word only enters the
pool via a 🤔 tap) and never flips back.
"""
from datetime import datetime, timezone

SCORE_MIN = 0
SCORE_MAX = 5
_NUMERIC = ("score", "correct", "incorrect", "dontknow_clicks", "quizzes")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: int) -> int:
    return max(SCORE_MIN, min(SCORE_MAX, value))


def _derive(rec: dict) -> None:
    """Recompute learned/in_review from the current score."""
    rec["learned"] = rec["score"] >= SCORE_MAX
    rec["in_review"] = bool(rec.get("drained")) and not rec["learned"]


def normalize(rec: dict) -> dict:
    """Backfill new fields and migrate the legacy `retired` flag, in place."""
    retired = bool(rec.pop("retired", False))
    if "score" not in rec:  # seed a score for legacy/new records
        rec["score"] = (
            SCORE_MAX if retired
            else _clamp(rec.get("correct", 0) - rec.get("incorrect", 0))
        )
    for key in _NUMERIC:
        rec.setdefault(key, 0)
    rec.setdefault("drained", True)  # pool words are added via a 🤔 tap
    rec.setdefault("added", now_iso())
    rec.setdefault("updated", rec["added"])
    _derive(rec)
    return rec


def record_answer(rec: dict, correct: bool) -> None:
    normalize(rec)
    if correct:
        rec["correct"] += 1
        rec["score"] = _clamp(rec["score"] + 1)
    else:
        rec["incorrect"] += 1
        rec["score"] = _clamp(rec["score"] - 1)
    _derive(rec)
    rec["updated"] = now_iso()


def record_dontknow(rec: dict) -> None:
    normalize(rec)
    rec["dontknow_clicks"] += 1
    rec["score"] = 0
    rec["drained"] = True
    _derive(rec)
    rec["updated"] = now_iso()


def record_quiz_sent(rec: dict) -> None:
    normalize(rec)
    rec["quizzes"] += 1
    rec["updated"] = now_iso()
