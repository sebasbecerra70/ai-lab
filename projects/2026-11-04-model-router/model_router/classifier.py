"""Logistic regression from scratch (batch gradient descent with L2)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .features import FEATURE_NAMES, extract


def _sigmoid(z: float) -> float:
    if z < -30:
        return 0.0
    if z > 30:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


@dataclass
class DifficultyClassifier:
    lr: float = 0.3
    epochs: int = 600
    l2: float = 0.05
    weights: list[float] = field(default_factory=list)
    bias: float = 0.0
    means: list[float] = field(default_factory=list)
    stds: list[float] = field(default_factory=list)

    def _scale(self, x: list[float]) -> list[float]:
        return [(v - m) / s for v, m, s in zip(x, self.means, self.stds)]

    def fit(self, texts: list[str], labels: list[int]) -> "DifficultyClassifier":
        X = [extract(t) for t in texts]
        n, d = len(X), len(X[0])
        self.means = [sum(r[j] for r in X) / n for j in range(d)]
        self.stds = [
            math.sqrt(sum((r[j] - self.means[j]) ** 2 for r in X) / n) or 1.0 for j in range(d)
        ]
        Xs = [self._scale(r) for r in X]
        self.weights, self.bias = [0.0] * d, 0.0
        for _ in range(self.epochs):
            gw, gb = [0.0] * d, 0.0
            for x, y in zip(Xs, labels):
                err = _sigmoid(sum(w * v for w, v in zip(self.weights, x)) + self.bias) - y
                for j in range(d):
                    gw[j] += err * x[j]
                gb += err
            self.weights = [w - self.lr * (g / n + self.l2 * w) for w, g in zip(self.weights, gw)]
            self.bias -= self.lr * gb / n
        return self

    def predict_proba(self, text: str) -> float:
        """Probability that the prompt is hard."""
        x = self._scale(extract(text))
        return _sigmoid(sum(w * v for w, v in zip(self.weights, x)) + self.bias)

    def top_features(self, k: int = 3) -> list[tuple[str, float]]:
        pairs = sorted(zip(FEATURE_NAMES, self.weights), key=lambda p: -abs(p[1]))
        return [(n, round(w, 2)) for n, w in pairs[:k]]
