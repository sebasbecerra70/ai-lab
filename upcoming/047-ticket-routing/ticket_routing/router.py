"""Nearest-centroid (Rocchio) router with a confidence + margin gate and a human-triage fallback."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .tfidf import TfIdf, Vector, cosine, l2

TRIAGE = "triage"


@dataclass
class Route:
    queue: str               # chosen queue, or "triage"
    best: str                # top-scoring queue even when we fall back
    score: float             # cosine similarity to the best centroid
    margin: float            # best minus runner-up
    reason: str = ""

    @property
    def fell_back(self) -> bool:
        return self.queue == TRIAGE


class CentroidRouter:
    def __init__(self, min_score: float = 0.12, min_margin: float = 0.06, min_df: int = 2):
        self.min_score, self.min_margin = min_score, min_margin
        self.vec = TfIdf(min_df)
        self.centroids: dict[str, Vector] = {}

    def fit(self, texts: list[str], queues: list[str]) -> "CentroidRouter":
        self.vec.fit(texts)
        sums: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        counts: dict[str, int] = defaultdict(int)
        for text, q in zip(texts, queues):
            counts[q] += 1
            for k, v in self.vec.transform(text).items():
                sums[q][k] += v
        self.centroids = {q: l2({k: v / counts[q] for k, v in s.items()}) for q, s in sums.items()}
        return self

    def scores(self, text: str) -> list[tuple[str, float]]:
        v = self.vec.transform(text)
        return sorted(((q, cosine(v, c)) for q, c in self.centroids.items()), key=lambda x: -x[1])

    def route(self, text: str) -> Route:
        ranked = self.scores(text)
        (best, s1), (_, s2) = ranked[0], ranked[1]
        margin = s1 - s2
        if s1 < self.min_score:
            return Route(TRIAGE, best, s1, margin, "no queue is similar enough")
        if margin < self.min_margin:
            return Route(TRIAGE, best, s1, margin, f"too close to call vs {ranked[1][0]}")
        return Route(best, best, s1, margin)

    def explain(self, text: str, queue: str, k: int = 3) -> list[str]:
        """Terms that contributed most to the match with `queue`."""
        v, c = self.vec.transform(text), self.centroids[queue]
        return [t for t, _ in sorted(((t, x * c.get(t, 0.0)) for t, x in v.items()), key=lambda x: -x[1])[:k] if _ > 0]
