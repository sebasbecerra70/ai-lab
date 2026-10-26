"""Features, a from-scratch L2-regularized logistic regression, and threshold/cost analysis."""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

COUNT_COLS = ["reallocated_sectors", "pending_sectors", "uncorrectable_errors", "crc_errors"]
NUM_COLS = ["power_on_hours", "temperature_c", "seek_error_rate"]
MODELS = ["HX-12T", "SG-16T"]  # one-hot; HX-8T is the reference


def load(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def features(row: dict) -> dict[str, float]:
    """Counts are heavy-tailed, so log1p them; hours in units of 10k for readable coefficients."""
    x = {c: math.log1p(float(row[c])) for c in COUNT_COLS}
    x["power_on_hours"] = float(row["power_on_hours"]) / 10_000
    x["temperature_c"] = float(row["temperature_c"])
    x["seek_error_rate"] = float(row["seek_error_rate"])
    for m in MODELS:
        x[f"model={m}"] = 1.0 if row["model"] == m else 0.0
    return x


FEATURES = COUNT_COLS + NUM_COLS + [f"model={m}" for m in MODELS]


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))


@dataclass
class Scaler:
    mean: dict[str, float]
    std: dict[str, float]

    @classmethod
    def fit(cls, xs: list[dict[str, float]]) -> "Scaler":
        n = len(xs)
        mean = {f: sum(x[f] for x in xs) / n for f in FEATURES}
        std = {f: math.sqrt(sum((x[f] - mean[f]) ** 2 for x in xs) / n) or 1.0 for f in FEATURES}
        return cls(mean, std)

    def transform(self, x: dict[str, float]) -> list[float]:
        return [(x[f] - self.mean[f]) / self.std[f] for f in FEATURES]


class LogisticRegression:
    def __init__(self, l2: float = 0.01, lr: float = 0.3, epochs: int = 400, pos_weight: float = 1.0):
        self.l2, self.lr, self.epochs, self.pos_weight = l2, lr, epochs, pos_weight
        self.w: list[float] = []
        self.b = 0.0

    def fit(self, X: list[list[float]], y: list[int]) -> "LogisticRegression":
        """Full-batch gradient descent. pos_weight up-weights the rare failures without resampling."""
        n, d = len(X), len(X[0])
        self.w = [0.0] * d
        # Start the bias at the base rate so early epochs aren't spent learning it.
        rate = min(max(sum(y) / n, 1e-6), 1 - 1e-6)
        self.b = math.log(rate / (1 - rate))
        total_w = sum(self.pos_weight if t else 1.0 for t in y)
        for _ in range(self.epochs):
            gw, gb = [0.0] * d, 0.0
            for xi, yi in zip(X, y):
                err = (sigmoid(self.b + sum(w * v for w, v in zip(self.w, xi))) - yi) * (self.pos_weight if yi else 1.0)
                gb += err
                for j, v in enumerate(xi):
                    gw[j] += err * v
            self.b -= self.lr * gb / total_w
            self.w = [w - self.lr * (g / total_w + self.l2 * w) for w, g in zip(self.w, gw)]
        return self

    def predict_proba(self, X: list[list[float]]) -> list[float]:
        return [sigmoid(self.b + sum(w * v for w, v in zip(self.w, xi))) for xi in X]


def stratified_split(rows: list[dict], test_share: float = 0.3, seed: int = 7) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    train, test = [], []
    for label in ("0", "1"):
        group = [r for r in rows if r["failed_30d"] == label]
        rng.shuffle(group)
        k = round(len(group) * test_share)
        test += group[:k]
        train += group[k:]
    return train, test


# ---- evaluation ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class AtThreshold:
    threshold: float
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def flagged(self) -> int:
        return self.tp + self.fp


def at_threshold(scores: list[float], y: list[int], t: float) -> AtThreshold:
    tp = sum(s >= t and v for s, v in zip(scores, y))
    fp = sum(s >= t and not v for s, v in zip(scores, y))
    fn = sum(s < t and v for s, v in zip(scores, y))
    return AtThreshold(t, tp, fp, fn, len(y) - tp - fp - fn)


def roc_auc(scores: list[float], y: list[int]) -> float:
    """Probability a random failing drive scores above a random healthy one (ties count half)."""
    pos = [s for s, v in zip(scores, y) if v]
    neg = [s for s, v in zip(scores, y) if not v]
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def average_precision(scores: list[float], y: list[int]) -> float:
    ranked = sorted(zip(scores, y), key=lambda t: -t[0])
    hits, total, ap = 0, sum(y), 0.0
    for i, (_, v) in enumerate(ranked, 1):
        if v:
            hits += 1
            ap += hits / i
    return ap / total if total else 0.0


@dataclass(frozen=True)
class Costs:
    """Per-drive costs. A surprise failure means an emergency swap, a degraded RAID rebuild and outage risk."""
    unplanned_failure: float = 2_400.0
    proactive_swap: float = 310.0  # new drive + planned tech time; also paid for every false alarm

    def total(self, r: AtThreshold) -> float:
        return r.fn * self.unplanned_failure + (r.tp + r.fp) * self.proactive_swap


def best_threshold(scores: list[float], y: list[int], costs: Costs) -> AtThreshold:
    candidates = sorted(set(round(s, 4) for s in scores)) + [1.01]
    return min((at_threshold(scores, y, t) for t in candidates), key=lambda r: (costs.total(r), -r.threshold))


def rule_baseline(rows: list[dict]) -> list[float]:
    """The classic ops rule: replace any drive with reallocated or pending sectors."""
    return [1.0 if int(r["reallocated_sectors"]) > 0 or int(r["pending_sectors"]) > 0 else 0.0 for r in rows]
