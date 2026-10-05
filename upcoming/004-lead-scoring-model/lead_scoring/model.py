"""Logistic regression from scratch (batch gradient descent + L2), metrics, and per-lead explanations."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .features import Standardizer, raw_features


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)  # numerically stable for large negative z
    return e / (1 + e)


class LogisticRegression:
    def __init__(self, lr: float = 0.3, epochs: int = 600, l2: float = 0.01):
        self.lr, self.epochs, self.l2 = lr, epochs, l2
        self.weights: list[float] = []
        self.bias = 0.0
        self.loss_history: list[float] = []

    def fit(self, X: list[list[float]], y: list[int]) -> "LogisticRegression":
        n, d = len(X), len(X[0])
        self.weights, self.bias = [0.0] * d, 0.0
        for _ in range(self.epochs):
            grad_w, grad_b, loss = [0.0] * d, 0.0, 0.0
            for xi, yi in zip(X, y):
                p = sigmoid(self.bias + sum(w * x for w, x in zip(self.weights, xi)))
                err = p - yi
                for j in range(d):
                    grad_w[j] += err * xi[j]
                grad_b += err
                loss -= yi * math.log(max(p, 1e-12)) + (1 - yi) * math.log(max(1 - p, 1e-12))
            # The L2 penalty keeps coefficients stable when features are correlated (visits vs pricing views).
            self.weights = [w - self.lr * (g / n + self.l2 * w) for w, g in zip(self.weights, grad_w)]
            self.bias -= self.lr * grad_b / n
            self.loss_history.append(loss / n)
        return self

    def predict_proba(self, x: list[float]) -> float:
        return sigmoid(self.bias + sum(w * v for w, v in zip(self.weights, x)))


def auc(y: list[int], scores: list[float]) -> float:
    """Rank-based AUC (Mann-Whitney U), with ties counted as half."""
    pos = [s for s, t in zip(scores, y) if t == 1]
    neg = [s for s, t in zip(scores, y) if t == 0]
    if not pos or not neg:
        raise ValueError("AUC needs both classes")
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def lift_at(y: list[int], scores: list[float], frac: float = 0.2) -> float:
    """Conversion rate in the top `frac` of scored leads divided by the overall conversion rate."""
    ranked = [t for _, t in sorted(zip(scores, y), key=lambda st: -st[0])]
    top = ranked[: max(1, int(len(ranked) * frac))]
    base = sum(y) / len(y)
    return (sum(top) / len(top)) / base if base else 0.0


@dataclass
class ScoredLead:
    lead_id: str
    company: str
    probability: float
    tier: str
    reasons: list[tuple[str, float]]  # (feature, contribution in log-odds)


class LeadScorer:
    """Standardize, fit, score, and explain. Tiers come from probability cut-offs that sales agrees on."""

    TIERS = [(0.5, "A"), (0.25, "B"), (0.0, "C")]

    def __init__(self, model: LogisticRegression | None = None):
        self.model = model or LogisticRegression()
        self.scaler = Standardizer()

    def fit(self, rows: list[dict]) -> "LeadScorer":
        feats = [raw_features(r) for r in rows]
        self.scaler.fit(feats)
        self.model.fit([self.scaler.transform(f) for f in feats], [int(r["converted"]) for r in rows])
        return self

    def coefficients(self) -> list[tuple[str, float]]:
        return sorted(zip(self.scaler.names, self.model.weights), key=lambda nw: -abs(nw[1]))

    def score(self, row: dict, top_n: int = 3) -> ScoredLead:
        x = self.scaler.transform(raw_features(row))
        p = self.model.predict_proba(x)
        # Contribution = weight × standardized value: how far this feature moves this lead from an average lead.
        contrib = [(n, w * v) for n, w, v in zip(self.scaler.names, self.model.weights, x)]
        contrib.sort(key=lambda c: -abs(c[1]))
        tier = next(t for cut, t in self.TIERS if p >= cut)
        return ScoredLead(row["lead_id"], row["company"], p, tier, contrib[:top_n])


def train_test_split(rows: list[dict], test_frac: float = 0.25, seed: int = 3) -> tuple[list[dict], list[dict]]:
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    cut = int(len(shuffled) * (1 - test_frac))
    return shuffled[:cut], shuffled[cut:]
