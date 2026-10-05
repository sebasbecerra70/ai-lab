"""Turn noisy OCR text into count features: words, word bigrams and (optionally) character n-grams."""
from __future__ import annotations

import re
from collections import Counter

NUM = re.compile(r"\d[\d,.\-/x]*")


def normalize(text: str) -> str:
    # numbers carry layout signal ("12 x 40 x 30", "1-85") but their values are noise
    return NUM.sub(" 0 ", text.lower())


def words(text: str) -> list[str]:
    return re.findall(r"[a-z/]+|0", normalize(text))


def featurize(text: str, char_n: int = 0) -> Counter:
    """Bag of features. char_n > 0 adds character n-grams inside words, which survive OCR typos
    ("componennts" still shares most 4-grams with "components")."""
    w = words(text)
    feats = Counter(w)
    feats.update(f"{a}_{b}" for a, b in zip(w, w[1:]))
    if char_n:
        for tok in w:
            if len(tok) >= char_n:
                padded = f"<{tok}>"
                feats.update(f"#{padded[i:i + char_n]}" for i in range(len(padded) - char_n + 1))
    return feats
