"""Tokenizing, light stemming and TF-IDF into sparse, L2-normalized vectors."""
from __future__ import annotations

import math
import re
from collections import Counter

Vector = dict[str, float]

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset("""
a an the and or of to in on for is are be by with at as it this that from we our us you your i me my
please would should could can so when all every keep need needs want let use via before after into
""".split())


# Domain synonyms, applied before tokenizing. A short hand-made list is cheap and fixes the
# splits that bag-of-words gets wrong ("single sign-on" vs "SSO", "Teams" the product vs "IT team",
# and Slack/Teams asks that are really one "chat notifications" theme).
SYNONYMS = [
    (re.compile(r"single sign[- ]on"), "sso"),
    (re.compile(r"\b(microsoft )?teams\b"), "msteam chatops"),
    (re.compile(r"\bslack\b"), "slack chatops"),
    (re.compile(r"\bxlsx\b"), "excel"),
]


def stem(word: str) -> str:
    """Tiny suffix stripper: enough to merge 'notifications'/'notification' and 'exporting'/'export'."""
    if word.endswith(("ss", "us")):
        return word
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    text = text.lower()
    for pattern, replacement in SYNONYMS:
        text = pattern.sub(replacement, text)
    return [stem(t) for t in _TOKEN.findall(text) if len(t) > 1 and t not in _STOP]


def normalize(vec: Vector) -> Vector:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()} if norm else {}


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class TfidfVectorizer:
    def __init__(self, min_df: int = 2):
        # Terms seen in only one request are usually typos or account names; they make clusters noisy.
        self.min_df = min_df
        self.idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> "TfidfVectorizer":
        df = Counter(t for text in texts for t in set(tokenize(text)))
        n = len(texts)
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items() if f >= self.min_df}
        return self

    def transform(self, texts: list[str]) -> list[Vector]:
        out = []
        for text in texts:
            tf = Counter(t for t in tokenize(text) if t in self.idf)
            out.append(normalize({t: c * self.idf[t] for t, c in tf.items()}))
        return out

    def fit_transform(self, texts: list[str]) -> list[Vector]:
        return self.fit(texts).transform(texts)
