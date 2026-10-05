"""Analytic Hierarchy Process: weights from pairwise judgments, plus a consistency check."""
from __future__ import annotations

from dataclasses import dataclass

# Saaty's random consistency index by matrix size.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


@dataclass
class AHPResult:
    weights: dict[str, float]
    lambda_max: float
    consistency_index: float
    consistency_ratio: float

    @property
    def consistent(self) -> bool:
        return self.consistency_ratio < 0.10


def pairwise_matrix(criteria: list[str], comparisons: list[tuple[str, str, float]]) -> list[list[float]]:
    """Build a reciprocal matrix. (a, b, 3) means a is 3x as important as b."""
    idx = {c: i for i, c in enumerate(criteria)}
    n = len(criteria)
    m = [[1.0] * n for _ in range(n)]
    seen = set()
    for a, b, v in comparisons:
        if v <= 0:
            raise ValueError(f"judgment must be positive: {a} vs {b}")
        i, j = idx[a], idx[b]
        m[i][j], m[j][i] = float(v), 1.0 / float(v)
        seen.add(frozenset((a, b)))
    missing = n * (n - 1) // 2 - len(seen)
    if missing:
        raise ValueError(f"{missing} pairwise comparisons missing")
    return m


def principal_eigenvector(m: list[list[float]], iters: int = 200, tol: float = 1e-12) -> tuple[list[float], float]:
    """Power iteration; returns the normalized eigenvector (sums to 1) and lambda_max."""
    n = len(m)
    w = [1.0 / n] * n
    for _ in range(iters):
        nxt = [sum(m[i][j] * w[j] for j in range(n)) for i in range(n)]
        total = sum(nxt)
        nxt = [v / total for v in nxt]
        if max(abs(a - b) for a, b in zip(nxt, w)) < tol:
            w = nxt
            break
        w = nxt
    mw = [sum(m[i][j] * w[j] for j in range(n)) for i in range(n)]
    lam = sum(mw[i] / w[i] for i in range(n)) / n
    return w, lam


def ahp_weights(criteria: list[str], comparisons: list[tuple[str, str, float]]) -> AHPResult:
    m = pairwise_matrix(criteria, comparisons)
    w, lam = principal_eigenvector(m)
    n = len(criteria)
    ci = (lam - n) / (n - 1) if n > 1 else 0.0
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri else 0.0
    return AHPResult(dict(zip(criteria, w)), lam, ci, cr)
