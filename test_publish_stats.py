"""Run: python test_publish_stats.py (no framework needed)."""
from publish_stats import compute

words = [
    {"es": "perro", "en": "dog", "score": 5},       # learned
    {"es": "gato", "en": "cat", "score": 2},        # in review
    {"es": "casa", "en": "house", "score": 3},      # in review
    {"es": "luz", "en": "light", "retired": True},  # legacy flag -> learned
]
s = compute(words, "2026-10-19")
assert s == {"date": "2026-10-19", "learned": 2, "in_review": 2, "avg_score": 2.5}, s
assert set(s) == {"date", "learned", "in_review", "avg_score"}  # never leaks words
assert compute([], "2026-10-19")["avg_score"] == 0
print("ok")
