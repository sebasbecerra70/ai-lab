"""Tokenizing shared by the lexical (BM25) and dense (hashed embedding) retrievers."""
from __future__ import annotations

import re

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its my me not of on or so that the "
    "their then there this to under use was what when where which who will with you your".split()
)


def tokens(text: str) -> list[str]:
    """Lowercase word tokens; keeps codes like e4012, sev1 and wi-fi parts intact as words."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def char_ngrams(word: str, lo: int = 3, hi: int = 5) -> list[str]:
    """fastText-style subwords with boundary markers: 'pass' -> '<pa', 'pas', 'ass', 'ss>', ..."""
    w = f"<{word}>"
    return [w[i:i + n] for n in range(lo, hi + 1) for i in range(len(w) - n + 1)]
