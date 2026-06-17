"""One-time parser: extract Spanish->English lookups from the Google
Takeout activity export into data/words.json."""
import html
import json
import re
import urllib.parse
from pathlib import Path

INPUT = Path(__file__).parent / "input" / "MyActivity.html"
OUTPUT = Path(__file__).parent / "data" / "words.json"

PATTERN = re.compile(r'translate\.google\.com/\?sl=es&amp;tl=en&amp;q=([^"]+)"')


def main() -> None:
    raw = INPUT.read_text(encoding="utf-8", errors="replace")
    seen = set()
    words = []
    for match in PATTERN.finditer(raw):
        word = html.unescape(urllib.parse.unquote_plus(match.group(1))).strip()
        if not word or word.casefold() in seen:
            continue
        seen.add(word.casefold())
        words.append(word)
    words.sort(key=str.casefold)

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(words)} words to {OUTPUT}")


if __name__ == "__main__":
    main()
