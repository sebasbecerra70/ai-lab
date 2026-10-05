"""Agreement statistics between the judge and human labels."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .judge import PairVerdict


def cohens_kappa(a: list, b: list) -> float:
    """Chance-corrected agreement between two raters over the same items."""
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label lists")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def spearman(x: list[float], y: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1  # average rank for ties
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return cov / var if var else 0.0


@dataclass(frozen=True)
class PairwiseReport:
    n: int
    flip_rate: float  # share of pairs whose verdict changed when the order was swapped
    first_position_win_rate: float  # among decisive raw calls, how often the first-shown answer won
    single_pass_agreement: float  # judge asked once (A first) vs humans
    swapped_agreement: float  # swap-consistent verdict vs humans
    swapped_kappa: float


def pairwise_report(verdicts: list[PairVerdict], human: list[str]) -> PairwiseReport:
    n = len(verdicts)
    raw = [(v.forward, "A") for v in verdicts] + [(v.backward, "B") for v in verdicts]
    decisive = [(w, first) for w, first in raw if w != "tie"]
    first_wins = sum(w == first for w, first in decisive)
    return PairwiseReport(
        n=n,
        flip_rate=sum(not v.consistent for v in verdicts) / n,
        first_position_win_rate=first_wins / len(decisive) if decisive else 0.0,
        single_pass_agreement=sum(v.forward == h for v, h in zip(verdicts, human)) / n,
        swapped_agreement=sum(v.winner == h for v, h in zip(verdicts, human)) / n,
        swapped_kappa=cohens_kappa([v.winner for v in verdicts], human),
    )
