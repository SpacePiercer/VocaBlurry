"""One-off: set the bot's profile texts so the emoji-only 🤔 button is explained.

Run locally (or via the workflow's manual dispatch) once, or whenever the wording
changes. Reads TELEGRAM_BOT_TOKEN from the environment.

- short description: shown on the bot's profile page (max 120 chars).
- description: shown in the chat when it's empty, before /start (max 512 chars).
"""
import os
import sys

import requests

SHORT_DESCRIPTION = (
    "Spanish→English vocab with blurred answers + daily quizzes. "
    "Tap \U0001f914 under a word to flag ones you didn't recall."
)

DESCRIPTION = (
    "I send a random Spanish word every couple of hours during the day, with the "
    "English translation blurred so you can test yourself before revealing it. "
    "Tap the \U0001f914 button under a word to flag one you didn't remember — "
    "those get logged for review. At the end of the day I send a quick quiz on the "
    "words you saw."
)


def call(token: str, method: str, payload: dict) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=30
    )
    if not resp.ok:
        print(f"{method} error {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
    print(f"{method}: ok")


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    call(token, "setMyShortDescription", {"short_description": SHORT_DESCRIPTION})
    call(token, "setMyDescription", {"description": DESCRIPTION})


if __name__ == "__main__":
    main()
