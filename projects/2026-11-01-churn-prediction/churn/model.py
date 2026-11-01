"""Logistic regression from scratch, with one-hot encoding, standardization and per-driver explanations."""
from __future__ import annotations

import math
import random

from .cohorts import Account

NUMERIC = ("onboarding_completed", "active_days_first30", "integrations_first30", "support_tickets_first30", "seats")
CATEGORICAL = {"plan": ("team", "business"), "billing": ("annual",)}  # baseline levels: starter, monthly
HORIZON = 6  # predict "cancels within the first 6 months" from first-30-day behaviour


def feature_names() -> list[str]:
    return list(NUMERIC) + [f"{k}={v}" for k, levels in CATEGORICAL.items() for v in levels]


def raw_features(a: Account) -> list[float]:
    return [float(getattr(a, f)) for f in NUMERIC] + [
        float(getattr(a, k) == v) for k, levels in CATEGORICAL.items() for v in levels]


def label(a: Account) -> int:
    return int(a.churn_month is not None and a.churn_month <= HORIZON)


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


class ChurnModel:
    def __init__(self, l2: float = 0.01, lr: float = 0.3, epochs: int = 600):
        self.l2, self.lr, self.epochs = l2, lr, epochs
        self.names = feature_names()
        self.mean: list[float] = []
        self.std: list[float] = []
        self.weights: list[float] = []
        self.bias = 0.0

    def _scale(self, x: list[float]) -> list[float]:
        return [(v - m) / s for v, m, s in zip(x, self.mean, self.std)]

    def fit(self, accounts: list[Account]) -> "ChurnModel":
        X = [raw_features(a) for a in accounts]
        y = [label(a) for a in accounts]
        if len(set(y)) < 2:
            raise ValueError("need both churned and retained accounts")
        n, d = len(X), len(X[0])
        self.mean = [sum(col) / n for col in zip(*X)]
        self.std = [math.sqrt(sum((v - m) ** 2 for v in col) / n) or 1.0 for col, m in zip(zip(*X), self.mean)]
        Xs = [self._scale(x) for x in X]
        self.weights, self.bias = [0.0] * d, math.log(sum(y) / (n - sum(y)))  # start at the base rate
        for _ in range(self.epochs):  # full-batch gradient descent on L2-penalized log loss
            grad_w, grad_b = [0.0] * d, 0.0
            for x, t in zip(Xs, y):
                err = sigmoid(self.bias + sum(w * v for w, v in zip(self.weights, x))) - t
                grad_b += err
                for j in range(d):
                    grad_w[j] += err * x[j]
            self.bias -= self.lr * grad_b / n
            self.weights = [w - self.lr * (g / n + self.l2 * w) for w, g in zip(self.weights, grad_w)]
        return self

    def predict(self, a: Account) -> float:
        x = self._scale(raw_features(a))
        return sigmoid(self.bias + sum(w * v for w, v in zip(self.weights, x)))

    def drivers(self) -> list[tuple[str, float]]:
        """Odds ratio for a one-standard-deviation increase in each feature, strongest effect first."""
        ors = [(n, math.exp(w)) for n, w in zip(self.names, self.weights)]
        return sorted(ors, key=lambda t: -abs(math.log(t[1])))

    def reasons(self, a: Account, top: int = 2) -> list[str]:
        """Features pushing this account's risk above an average account's."""
        x = self._scale(raw_features(a))
        contrib = sorted(((w * v, n) for w, v, n in zip(self.weights, x, self.names)), reverse=True)
        return [describe(n, a) for c, n in contrib[:top] if c > 0.1]


def describe(name: str, a: Account) -> str:
    if name == "onboarding_completed":
        return "onboarding not completed" if not a.onboarding_completed else "onboarding completed"
    if "=" in name:
        k = name.split("=")[0]
        return f"{k} {getattr(a, k)}"
    return f"{name.replace('_first30', '').replace('_', ' ')} {getattr(a, name)}"


def auc(y: list[int], p: list[float]) -> float:
    """Rank-based AUC (Mann-Whitney U) with tie handling."""
    order = sorted(range(len(p)), key=lambda i: p[i])
    ranks = [0.0] * len(p)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and p[order[j + 1]] == p[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    pos = sum(y)
    neg = len(y) - pos
    if not pos or not neg:
        raise ValueError("AUC needs both classes")
    return (sum(r for r, t in zip(ranks, y) if t) - pos * (pos + 1) / 2) / (pos * neg)


def split(accounts: list[Account], test_frac: float = 0.3, seed: int = 7) -> tuple[list[Account], list[Account]]:
    shuffled = accounts[:]
    random.Random(seed).shuffle(shuffled)
    cut = int(len(shuffled) * (1 - test_frac))
    return shuffled[:cut], shuffled[cut:]
