"""Robust multiplicative seasonal decomposition: value = trend x seasonal x (1 + residual)."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


def rolling_median(xs: list[float], window: int) -> list[float]:
    """Centered rolling median; the window shrinks at the edges. Medians ignore single spikes."""
    half = window // 2
    return [median(xs[max(0, i - half): i + half + 1]) for i in range(len(xs))]


@dataclass
class Decomposition:
    values: list[float]
    trend: list[float]
    seasonal: list[float]  # per-point factor relative to the median day (1.0 = typical)
    residual: list[float]  # relative deviation from trend x seasonal

    def expected(self, i: int) -> float:
        return self.trend[i] * self.seasonal[i]


def decompose(values: list[float], period: int = 7, trend_window: int | None = None) -> Decomposition:
    if len(values) < 2 * period:
        raise ValueError(f"need at least two full periods ({2 * period} points), got {len(values)}")
    # A window longer than the period keeps weekly shape out of the trend.
    trend = rolling_median(values, trend_window or 2 * period + 1)
    ratios = [v / t if t else 1.0 for v, t in zip(values, trend)]
    # Not renormalized to mean 1: the median trend tracks a typical day, so factors are relative to it.
    phase = [median(ratios[p::period]) for p in range(period)]
    seasonal = [phase[i % period] for i in range(len(values))]
    residual = [v / (t * s) - 1 if t * s else 0.0 for v, t, s in zip(values, trend, seasonal)]
    return Decomposition(values, trend, seasonal, residual)


def robust_z(xs: list[float]) -> list[float]:
    """Modified z-score (Iglewicz & Hoaglin): 0.6745 (x - median) / MAD.

    When more than half the points are identical, MAD is 0; fall back to the mean
    absolute deviation (scaled by 1.2533 to estimate a standard deviation).
    """
    med = median(xs)
    dev = [abs(x - med) for x in xs]
    mad = median(dev)
    if mad > 0:
        return [0.6745 * (x - med) / mad for x in xs]
    mean_ad = sum(dev) / len(dev)
    if mean_ad == 0:
        return [0.0] * len(xs)
    return [(x - med) / (1.2533 * mean_ad) for x in xs]


def naive_z(xs: list[float]) -> list[float]:
    """Classic z-score on raw values: the baseline that weekends and growth fool."""
    n = len(xs)
    mean = sum(xs) / n
    sd = (sum((x - mean) ** 2 for x in xs) / n) ** 0.5
    return [(x - mean) / sd if sd else 0.0 for x in xs]
