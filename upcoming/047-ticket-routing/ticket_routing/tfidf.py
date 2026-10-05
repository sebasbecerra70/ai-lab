"""TF-IDF vectors as sparse dicts: sublinear tf, smoothed idf, unigrams + bigrams, L2-normalized."""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an the and or but of to in on at for from with by is are was were be been it its this that i
me my we our you your he she they them pls please hi hello thanks team can could someone help asap urgent re
again since ticket look blocking just""".split())

Vector = dict[str, float]


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower()) if w not in STOP and len(w) > 1]
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


def l2(v: Vector) -> Vector:
    n = math.sqrt(sum(x * x for x in v.values()))
    return {k: x / n for k, x in v.items()} if n else {}


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


class TfIdf:
    def __init__(self, min_df: int = 2):
        self.min_df = min_df
        self.idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> "TfIdf":
        df = Counter(t for text in texts for t in set(tokens(text)))
        n = len(texts)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items() if c >= self.min_df}
        return self

    def transform(self, text: str) -> Vector:
        tf = Counter(t for t in tokens(text) if t in self.idf)
        return l2({t: (1 + math.log(c)) * self.idf[t] for t, c in tf.items()})
