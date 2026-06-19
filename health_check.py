"""Health check: a per-word table of quiz scores and activity.

Aggregates the daily feed log and the 🤔-flagged word pool into one Markdown
table written to the GitHub Actions step summary (and stdout for local runs).
Read-only — it never mutates any data file.

Columns:
  Score      running score in [0, 5] (see scoring.py)
  Learned    1 once the word reached score 5
  In review  1 while the word is in the pool (drained) and not yet learned
  Checks     times it appeared in the feed with a blurred translation
  Quizzes    times a quiz poll was sent for it
  Correct/Incorrect  quiz answers
  Accuracy   correct / (correct + incorrect)
  🤔 clicks  total "don't know" taps
  Drained    1 if it ever entered the review pool
  Last seen  most recent feed date
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

import scoring

DATA_DIR = Path(os.environ.get("VOCAB_DATA_DIR") or Path(__file__).parent / "data")
VOCAB_FILE = DATA_DIR / "vocab.json"
DAILY_DIR = DATA_DIR / "daily"
WORDS_FILE = DATA_DIR / "review" / "words.json"


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def norm(s: str) -> str:
    return (s or "").strip().casefold()


def gather() -> list[dict]:
    """One row per word that's appeared in the feed or is in the quiz pool."""
    pool = {norm(w["es"]): scoring.normalize(w) for w in load_json(WORDS_FILE, [])}
    vocab_en = {norm(e["es"]): e.get("en") for e in load_json(VOCAB_FILE, [])}

    checks: Counter = Counter()
    last_seen: dict[str, str] = {}
    display: dict[str, str] = {}  # normalized -> original es
    daily_en: dict[str, str] = {}
    for path in sorted(DAILY_DIR.glob("*.json")):
        date = path.stem
        for e in load_json(path, []):
            es = e.get("es")
            if not es:
                continue
            k = norm(es)
            checks[k] += 1
            last_seen[k] = max(last_seen.get(k, ""), date)
            display.setdefault(k, es)
            if e.get("en"):
                daily_en.setdefault(k, e["en"])

    rows = []
    for k in set(pool) | set(checks):
        rec = pool.get(k, {})
        es = rec.get("es") or display.get(k, k)
        en = rec.get("en") or daily_en.get(k) or vocab_en.get(k) or ""
        correct = rec.get("correct", 0)
        incorrect = rec.get("incorrect", 0)
        attempts = correct + incorrect
        rows.append(
            {
                "es": es,
                "en": en,
                "score": rec.get("score", 0),
                "learned": bool(rec.get("learned")),
                "in_review": bool(rec.get("in_review")),
                "checks": checks.get(k, 0),
                "quizzes": rec.get("quizzes", 0),
                "correct": correct,
                "incorrect": incorrect,
                "accuracy": round(100 * correct / attempts) if attempts else None,
                "dontknow": rec.get("dontknow_clicks", 0),
                "drained": 1 if rec.get("drained") else 0,
                "last_seen": last_seen.get(k, ""),
            }
        )
    return rows


def render(rows: list[dict]) -> str:
    # Surface struggling words first: in review, then lowest score, then most-seen.
    rows = sorted(
        rows, key=lambda r: (not r["in_review"], r["score"], -r["checks"], r["es"])
    )
    learned = sum(r["learned"] for r in rows)
    in_review = sum(r["in_review"] for r in rows)
    total_checks = sum(r["checks"] for r in rows)
    total_quizzes = sum(r["quizzes"] for r in rows)
    tot_correct = sum(r["correct"] for r in rows)
    tot_incorrect = sum(r["incorrect"] for r in rows)
    attempts = tot_correct + tot_incorrect
    acc = f"{round(100 * tot_correct / attempts)}%" if attempts else "—"

    out = [
        "# Vocab health check",
        "",
        f"**{len(rows)}** words seen · **{learned}** learned · "
        f"**{in_review}** in review · **{total_checks}** checks · "
        f"**{total_quizzes}** quizzes · accuracy **{acc}** "
        f"({tot_correct}/{attempts})",
        "",
        "| Word | English | Score | Learned | In review | Checks | Quizzes | "
        "Correct | Incorrect | Accuracy | 🤔 clicks | Drained | Last seen |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        acc_cell = f"{r['accuracy']}%" if r["accuracy"] is not None else "—"
        attention = " ⚠️" if r["in_review"] and r["score"] <= 1 else ""
        out.append(
            f"| {r['es']}{attention} | {r['en']} | {r['score']}/5 | "
            f"{int(r['learned'])} | {int(r['in_review'])} | {r['checks']} | "
            f"{r['quizzes']} | {r['correct']} | {r['incorrect']} | {acc_cell} | "
            f"{r['dontknow']} | {r['drained']} | {r['last_seen']} |"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    try:  # the table has emoji; avoid cp1252 errors on local Windows consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    report = render(gather())
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report)


if __name__ == "__main__":
    main()
