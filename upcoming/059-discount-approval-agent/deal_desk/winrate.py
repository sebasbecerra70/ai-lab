"""Logistic regression, from scratch, of win probability on discount, competition and segment. It answers
the question the discount is supposed to answer: does the extra discount actually buy the deal?"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

SEGMENTS = ["smb", "mid-market", "enterprise"]


def features(discount: float, competitor: bool, segment: str) -> list[float]:
    d = discount / 10
    return [1.0, d, d * d, float(competitor)] + [float(segment == s) for s in SEGMENTS[1:]]


@dataclass
class WinModel:
    weights: list[float]

    def p_win(self, discount: float, competitor: bool, segment: str) -> float:
        z = sum(w * x for w, x in zip(self.weights, features(discount, competitor, segment)))
        return 1 / (1 + math.exp(-z))


def load_history(path: Path) -> list[dict]:
    with open(path) as f:
        return [dict(r, discount=float(r["discount"]), competitor=r["competitor"] == "1", won=r["won"] == "1")
                for r in csv.DictReader(f)]


def fit(rows: list[dict], lr: float = 0.1, epochs: int = 3000, l2: float = 0.01) -> WinModel:
    """Batch gradient descent on log loss with a light L2 penalty (not on the intercept)."""
    X = [features(r["discount"], r["competitor"], r["segment"]) for r in rows]
    y = [1.0 if r["won"] else 0.0 for r in rows]
    w = [0.0] * len(X[0])
    n = len(X)
    for _ in range(epochs):
        grad = [0.0] * len(w)
        for xi, yi in zip(X, y):
            p = 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, xi))))
            for j, xj in enumerate(xi):
                grad[j] += (p - yi) * xj / n
        for j in range(len(w)):
            w[j] -= lr * (grad[j] + (l2 * w[j] if j else 0.0))
    return WinModel(w)


def log_loss(model: WinModel, rows: list[dict]) -> float:
    eps = 1e-9
    total = 0.0
    for r in rows:
        p = model.p_win(r["discount"], r["competitor"], r["segment"])
        total -= math.log(p + eps) if r["won"] else math.log(1 - p + eps)
    return total / len(rows)


def prior_discount(rows: list[dict], customer: str) -> float | None:
    mine = [r["discount"] for r in rows if r["customer"] == customer and r["won"]]
    return mine[-1] if mine else None
