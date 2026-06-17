"""One-time (re-runnable) step: translate every Spanish word in
data/words.json to English and write data/vocab.json as [{es, en}, ...].

Run locally whenever words.json changes:
    pip install deep-translator
    python translate_vocab.py
"""
import json
import sys
import time
from pathlib import Path

from deep_translator import GoogleTranslator

WORDS_FILE = Path(__file__).parent / "data" / "words.json"
VOCAB_FILE = Path(__file__).parent / "data" / "vocab.json"


def main() -> None:
    words = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    translator = GoogleTranslator(source="es", target="en")
    vocab = []
    for i, es in enumerate(words, 1):
        try:
            en = translator.translate(es) or ""
        except Exception as exc:  # noqa: BLE001 - skip words that fail to translate
            print(f"  ! failed on {es!r}: {exc}", file=sys.stderr)
            en = ""
        if en:
            vocab.append({"es": es, "en": en})
        if i % 25 == 0:
            print(f"  translated {i}/{len(words)}")
        time.sleep(0.05)  # be gentle with the free endpoint

    VOCAB_FILE.write_text(
        json.dumps(vocab, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(vocab)} entries to {VOCAB_FILE}")


if __name__ == "__main__":
    main()
