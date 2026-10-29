"""AdaBoost over decision stumps, from scratch.

Each stump asks one question ("weather_index <= 0.41?", "carrier == Crestway?") and votes +1 (delayed) or -1.
Boosting re-weights the shipments the ensemble still gets wrong, so later stumps focus on the hard cases.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .features import CATEGORICAL, NUMERIC


@dataclass(frozen=True)
class Stump:
    feature: str
    op: str  # "<=" for numeric, "==" for categorical
    value: float | str
    polarity: int  # +1: condition true -> delayed vote; -1: condition true -> on-time vote
    alpha: float = 0.0

    def test(self, x: dict) -> bool:
        v = x[self.feature]
        return v <= self.value if self.op == "<=" else v == self.value

    def vote(self, x: dict) -> int:
        return self.polarity if self.test(x) else -self.polarity

    def describe(self, x: dict) -> str:
        if self.op == "==":
            return f"{self.feature}={x[self.feature]}" + ("" if self.test(x) else f" (not {self.value})")
        side = "<=" if self.test(x) else ">"
        return f"{self.feature} {side} {self.value:g}"


def candidate_splits(X: list[dict], max_thresholds: int = 12) -> list[tuple[str, str, float | str]]:
    splits = []
    for f in NUMERIC:
        vals = sorted({x[f] for x in X})
        if len(vals) < 2:
            continue
        mids = [(a + b) / 2 for a, b in zip(vals, vals[1:])]
        step = max(1, len(mids) // max_thresholds)
        splits += [(f, "<=", round(m, 3)) for m in mids[::step]]
    for f in CATEGORICAL:
        vals = sorted({x[f] for x in X})
        # A binary flag needs one split, on its "on" value (yes / 1), so explanations read naturally.
        splits += [(f, "==", v) for v in (vals[-1:] if len(vals) == 2 else vals)]
    return splits


class StumpEnsemble:
    def __init__(self, rounds: int = 40):
        self.rounds = rounds
        self.stumps: list[Stump] = []

    def fit(self, X: list[dict], y: list[int]) -> "StumpEnsemble":
        if not X or len(X) != len(y):
            raise ValueError("X and y must be non-empty and the same length")
        if len(set(y)) < 2:
            raise ValueError("need both delayed and on-time shipments to learn from")
        signs = [1 if v else -1 for v in y]
        n = len(X)
        w = [1 / n] * n
        # Precompute each split's truth table once; boosting rounds then only re-sum weights.
        tables = [(s, [Stump(s[0], s[1], s[2], 1).test(x) for x in X]) for s in candidate_splits(X)]
        self.stumps = []
        for _ in range(self.rounds):
            best = None
            for (f, op, v), truth in tables:
                # weighted error if "condition true -> delayed"; the flipped stump has error 1 - err
                err = sum(wi for wi, t, s in zip(w, truth, signs) if (1 if t else -1) != s)
                for pol, e in ((1, err), (-1, 1 - err)):
                    if best is None or e < best[0]:
                        best = (e, f, op, v, pol, truth)
            err, f, op, v, pol, truth = best
            err = min(max(err, 1e-10), 1 - 1e-10)
            if err >= 0.5:
                break
            alpha = 0.5 * math.log((1 - err) / err)
            self.stumps.append(Stump(f, op, v, pol, alpha))
            w = [wi * math.exp(-alpha * s * (pol if t else -pol)) for wi, t, s in zip(w, truth, signs)]
            z = sum(w)
            w = [wi / z for wi in w]
        return self

    def margin(self, x: dict) -> float:
        return sum(s.alpha * s.vote(x) for s in self.stumps)

    def predict_proba(self, x: dict) -> float:
        # AdaBoost's margin estimates half the log-odds (Friedman, Hastie & Tibshirani 2000).
        return 1 / (1 + math.exp(-2 * self.margin(x)))

    def contributions(self, x: dict) -> dict[str, float]:
        """Signed margin contribution per feature: positive pushes toward 'delayed'."""
        out: dict[str, float] = {}
        for s in self.stumps:
            out[s.feature] = out.get(s.feature, 0.0) + s.alpha * s.vote(x)
        return out

    def reasons(self, x: dict, top: int = 2) -> list[str]:
        by_feature: dict[str, tuple[float, str]] = {}
        for s in self.stumps:
            c = s.alpha * s.vote(x)
            if c > 0 and c > by_feature.get(s.feature, (0, ""))[0]:
                by_feature[s.feature] = (c, s.describe(x))
        totals = self.contributions(x)
        ranked = sorted((f for f in by_feature if totals[f] > 0), key=lambda f: -totals[f])
        return [by_feature[f][1] for f in ranked[:top]]

    def importance(self) -> dict[str, float]:
        total = sum(s.alpha for s in self.stumps) or 1.0
        imp: dict[str, float] = {}
        for s in self.stumps:
            imp[s.feature] = imp.get(s.feature, 0.0) + s.alpha / total
        return dict(sorted(imp.items(), key=lambda kv: -kv[1]))
