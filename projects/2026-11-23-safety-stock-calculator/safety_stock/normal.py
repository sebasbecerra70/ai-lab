"""Standard normal helpers built on math.erf: cdf, pdf, inverse cdf and the unit loss function."""
from __future__ import annotations

import math


def pdf(z: float) -> float:
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)


def cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def ppf(p: float) -> float:
    """Inverse CDF by bisection: plenty fast for a few hundred SKUs and exact to 1e-10."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    lo, hi = -10.0, 10.0
    while hi - lo > 1e-10:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) < p else (lo, mid)
    return (lo + hi) / 2


def loss(z: float) -> float:
    """Standard normal loss G(z) = E[(Z - z)+]: expected units short per unit of sigma."""
    return pdf(z) - z * (1 - cdf(z))


def z_for_loss(target: float) -> float:
    """Inverse of the (decreasing) loss function."""
    lo, hi = -5.0, 8.0
    while hi - lo > 1e-10:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if loss(mid) > target else (lo, mid)
    return (lo + hi) / 2
