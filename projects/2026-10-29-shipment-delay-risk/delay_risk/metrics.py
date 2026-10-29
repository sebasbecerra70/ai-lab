"""Holdout metrics, written out so the numbers in a review are easy to check."""
from __future__ import annotations

import math


def auc(y: list[int], p: list[float]) -> float:
    """Probability that a random delayed shipment scores above a random on-time one (ties count half)."""
    pos = [s for s, t in zip(p, y) if t]
    neg = [s for s, t in zip(p, y) if not t]
    if not pos or not neg:
        raise ValueError("AUC needs both classes")
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def brier(y: list[int], p: list[float]) -> float:
    return sum((pi - yi) ** 2 for yi, pi in zip(y, p)) / len(y)


def log_loss(y: list[int], p: list[float], eps: float = 1e-6) -> float:
    return -sum(yi * math.log(max(pi, eps)) + (1 - yi) * math.log(max(1 - pi, eps)) for yi, pi in zip(y, p)) / len(y)


def precision_at(y: list[int], p: list[float], k: int) -> float:
    """Of the k riskiest shipments, how many were actually late? This is the list a planner acts on."""
    top = sorted(zip(p, y), key=lambda t: -t[0])[:k]
    return sum(t for _, t in top) / len(top)
