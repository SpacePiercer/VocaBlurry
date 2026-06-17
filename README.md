# VocaBlurry

A Telegram vocab bot that sends random Spanish words during the day with the
English translation **blurred** (tap-to-reveal spoiler) so you can self-test,
lets you flag words you didn't remember with a 🤔 button, and quizzes you on the
day's words each evening. Runs entirely on GitHub Actions cron — no server.

## How it works

- **Word posts** (`send_word.py`) — every 2h in the daytime, a random `{es, en}`
  entry is sent with the translation as a `tg-spoiler`, plus a single 🤔 button.
- **Forgotten-word tracking** (`drain_updates.py`) — tapping 🤔 queues a Telegram
  `callback_query`; a twice-daily job reads them via `getUpdates` (serverless, no
  webhook), logs the words you blanked on, and adds them to the quiz pool. Taps are
  deduped and the button locks to ✅ once recorded. The same job reads quiz
  `poll_answer`s to track per-word progress.
- **Adaptive nightly quiz** (`send_quiz.py`) — quizzes only your flagged
  ("problematic") words, as native quiz polls. Each night it takes a weighted
  sample without replacement (weight `(incorrect+1)/(correct+1)`, so often-missed
  words appear more), capped at `MAX_QUIZ` (8). A word retires from the pool after
  `RETIRE_AT` (5) correct answers. Empty pool → no quiz.

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
- `send_word.py` — sends a word with a blurred translation + 🤔 button.
- `drain_updates.py` — drains 🤔 taps into `data/review/forgotten.json`, maintains
  the quiz pool + per-word stats in `data/review/words.json`, and scores quiz
  answers against `data/state/pending_polls.json`. Must be the bot's only
  `getUpdates` consumer.
- `send_quiz.py` — sends the adaptive nightly quiz; records each poll in
  `data/state/pending_polls.json` for the drain to score (`MAX_QUIZ`/`RETIRE_AT`
  are tunable constants at the top of the file).
- `set_bot_meta.py` — one-off: sets the bot's profile description (explains 🤔).
- `.github/workflows/` — `vocab.yml` (sends 6×/day), `drain.yml` (drains 2×/day),
  `quiz.yml` (daily quiz).

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
