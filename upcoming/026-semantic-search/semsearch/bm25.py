"""Okapi BM25: the lexical baseline that still wins on exact tokens like error codes and product names."""
from __future__ import annotations

import math

from .text import tokens


class BM25:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.ids: list[str] = []
        self.tfs: list[dict[str, int]] = []
        self.lengths: list[int] = []
        self.df: dict[str, int] = {}

    def fit(self, docs: list[tuple[str, str]]) -> "BM25":
        for doc_id, text in docs:
            tf: dict[str, int] = {}
            for t in tokens(text):
                tf[t] = tf.get(t, 0) + 1
            self.ids.append(doc_id)
            self.tfs.append(tf)
            self.lengths.append(sum(tf.values()))
            for t in tf:
                self.df[t] = self.df.get(t, 0) + 1
        self.avgdl = sum(self.lengths) / len(self.lengths)
        return self

    def idf(self, term: str) -> float:
        n, df = len(self.ids), self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))  # the +1 keeps very common terms non-negative

    def score(self, query: str, i: int) -> float:
        tf, dl = self.tfs[i], self.lengths[i]
        s = 0.0
        for t in set(tokens(query)):
            f = tf.get(t, 0)
            if f:
                s += self.idf(t) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def search(self, query: str, k: int = 5) -> list[tuple[str, float]]:
        scored = [(self.ids[i], self.score(query, i)) for i in range(len(self.ids))]
        return sorted([s for s in scored if s[1] > 0], key=lambda t: (-t[1], t[0]))[:k]
