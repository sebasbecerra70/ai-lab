"""Which assumptions move the answer? Tornado (one at a time) and a two-way grid."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .model import Market, Sizing, bottom_up


@dataclass
class Bar:
    name: str
    low_value: float
    high_value: float
    swing: float


def tornado(m: Market, metric: Callable[[Sizing], float] = lambda s: s.som,
            model: Callable[..., Sizing] = bottom_up) -> tuple[float, list[Bar]]:
    base = metric(model(m))
    bars = []
    for name, a in m.assumptions.items():
        if a.low == a.high:
            continue
        lo, hi = metric(model(m, {name: a.low})), metric(model(m, {name: a.high}))
        bars.append(Bar(name, lo, hi, abs(hi - lo)))
    bars.sort(key=lambda b: -b.swing)
    return base, [b for b in bars if b.swing > 0]


def two_way(m: Market, row: str, col: str, metric: Callable[[Sizing], float] = lambda s: s.som,
            model: Callable[..., Sizing] = bottom_up, steps: int = 3) -> tuple[list[float], list[float], list[list[float]]]:
    def grid(a):
        return [a.low + (a.high - a.low) * i / (steps - 1) for i in range(steps)]
    rows, cols = grid(m.assumptions[row]), grid(m.assumptions[col])
    table = [[metric(model(m, {row: r, col: c})) for c in cols] for r in rows]
    return rows, cols, table
