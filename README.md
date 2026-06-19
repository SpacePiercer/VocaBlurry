# VocaBlurry

A Telegram vocab bot that sends random Spanish words during the day with the
English translation **blurred** (tap-to-reveal spoiler) so you can self-test,
lets you flag words you didn't remember with a 🤔 button, and quizzes you on the
words you flagged each evening. Runs entirely on GitHub Actions cron — no server.

## How it works

- **Word posts** (`send_word.py`) — every 2h in the daytime, a random single-word
  `{es, en}` entry (multi-word phrases and already-learned words are skipped) is
  sent with the translation as a `tg-spoiler`, plus a single 🤔 button.
- **Forgotten-word tracking** (`drain_updates.py`) — tapping 🤔 queues a Telegram
  `callback_query`; a twice-daily job reads them via `getUpdates` (serverless, no
  webhook), logs the words you blanked on, and adds them to the quiz pool (resetting
  their score to 0). Taps are deduped and the button locks to ✅ once recorded. The
  same job reads quiz `poll_answer`s to move each word's score.
- **Adaptive nightly quiz** (`send_quiz.py`) — quizzes only your in-review words
  (flagged, not yet learned), as native quiz polls. Each night it takes a weighted
  sample without replacement (weight `(incorrect+1)/(correct+1)`, so often-missed
  words appear more), capped at `MAX_QUIZ` (8). Empty pool → no quiz.
- **Health check** (`health_check.py`) — a per-word table of scores and activity
  rendered to the Actions step summary (on demand or daily).

### Scoring & learning

Each pool word carries a running `score` in `[0, 5]` in `data/review/words.json`,
updated as events are processed in chronological order:

- Correct quiz answer → `+1` (capped at 5); incorrect → `-1` (floored at 0).
- A 🤔 tap resets the score to 0 (and re-enters review).
- `learned` is `score == 5` (leaves the quiz pool); `in_review` is a pooled word
  that isn't learned yet. `correct`/`incorrect` are kept as lifetime totals.

(This replaces the older retire-after-5-correct rule; the legacy `retired` flag is
migrated to `learned` automatically.)

### Two-repo layout (code public, data private)

Code lives here (public). All mutable data — your vocabulary, daily logs,
forgotten words, the `getUpdates` offset — lives in a **separate private repo**
so it's never exposed. Each workflow checks the private repo out into
`data-repo/` and points the scripts at it via `VOCAB_DATA_DIR`, then commits any
changes back there. Scripts default to `./data` when `VOCAB_DATA_DIR` is unset
(handy for local runs).

## Files

- `parse_activity.py` / `translate_vocab.py` — one-time local steps that turn a
  Google Takeout activity export into `data/vocab.json` (`[{es, en}, ...]`).
- `send_word.py` — sends a single, not-yet-learned word with a blurred translation
  + 🤔 button.
- `drain_updates.py` — drains 🤔 taps into `data/review/forgotten.json`, maintains
  the quiz pool + per-word scores in `data/review/words.json`, and scores quiz
  answers against `data/state/pending_polls.json`. Must be the bot's only
  `getUpdates` consumer.
- `scoring.py` — shared per-word scoring/learning state (running 0–5 score,
  learned/in-review derivation, legacy `retired` migration).
- `send_quiz.py` — sends the adaptive nightly quiz; records each poll in
  `data/state/pending_polls.json` for the drain to score (`MAX_QUIZ` is a tunable
  constant at the top of the file).
- `health_check.py` — renders the per-word scores table to the Actions step summary.
- `set_bot_meta.py` — one-off: sets the bot's profile description (explains 🤔).
- `.github/workflows/` — `vocab.yml` (sends 6×/day), `drain.yml` (drains 2×/day),
  `quiz.yml` (daily quiz), `health.yml` (daily/on-demand scores table).

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather), copy the **token**, and
   press **Start** in the bot chat. Get your chat ID from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
2. Create a **private** repo for the data (this project expects
   `SpacePiercer/vocablurry-data`) holding your `data/` directory.
3. Create a **fine-grained PAT** scoped to that private data repo with
   **Contents: Read and write**.
4. In **this** repo: Settings → Secrets and variables → Actions, add:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `DATA_REPO_TOKEN` (the PAT).
5. Actions tab → run any workflow manually to test.

## Notes

- GitHub cron is UTC and can lag a few minutes under load; daytime times are PDT
  and shift an hour earlier in winter (PST).
- `getUpdates` and webhooks are mutually exclusive — only `drain_updates.py`
  consumes updates, tracking its cursor in `data/state/offset.json`.
- GitHub disables schedules in repos with no pushes for 60 days; any commit
  re-enables them.
