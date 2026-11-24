"""Safety stock when both demand and lead time vary, for cycle-service or fill-rate targets."""
from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

from . import normal


@dataclass
class Sku:
    sku: str
    description: str
    unit_cost: float
    order_qty: float
    abc: str
    d: float = 0.0       # mean weekly demand
    sd_d: float = 0.0    # std dev of weekly demand
    lt: float = 0.0      # mean lead time, weeks
    sd_lt: float = 0.0   # std dev of lead time, weeks

    @property
    def sigma_ltd(self) -> float:
        """Std dev of demand over the lead time, with both sources of variance:
        Var = LT * sd_d^2  (demand noise over LT weeks)  +  d^2 * sd_lt^2  (uncertain number of weeks)."""
        return math.sqrt(self.lt * self.sd_d ** 2 + self.d ** 2 * self.sd_lt ** 2)

    @property
    def sigma_demand_only(self) -> float:
        return math.sqrt(self.lt) * self.sd_d

    @property
    def lt_share(self) -> float:
        """Share of lead-time-demand variance caused by supplier lead-time variability."""
        return (self.d ** 2 * self.sd_lt ** 2) / self.sigma_ltd ** 2


def load(folder: Path) -> list[Sku]:
    with open(folder / "skus.csv") as f:
        skus = {r["sku"]: Sku(r["sku"], r["description"], float(r["unit_cost"]), float(r["order_qty"]), r["abc"])
                for r in csv.DictReader(f)}
    with open(folder / "demand.csv") as f:
        rows = list(csv.DictReader(f))
    for s in skus.values():
        series = [float(r[s.sku]) for r in rows]
        s.d, s.sd_d = statistics.mean(series), statistics.stdev(series)
    lts: dict[str, list[float]] = {}
    with open(folder / "receipts.csv") as f:
        for r in csv.DictReader(f):
            lts.setdefault(r["sku"], []).append(float(r["lead_time_weeks"]))
    for s in skus.values():
        s.lt, s.sd_lt = statistics.mean(lts[s.sku]), statistics.stdev(lts[s.sku])
    return list(skus.values())


def safety_stock_csl(s: Sku, csl: float) -> float:
    """Cycle service level: probability of no stockout in a replenishment cycle."""
    return max(0.0, normal.ppf(csl) * s.sigma_ltd)


def safety_stock_fill(s: Sku, fill_rate: float) -> float:
    """Fill rate: share of demand served from stock. Expected shortage per cycle = sigma_LTD * G(z) must be
    <= (1 - fill) * Q. Bigger orders mean fewer exposures, so fill-rate safety stock falls as Q grows."""
    target = (1 - fill_rate) * s.order_qty / s.sigma_ltd
    return max(0.0, normal.z_for_loss(target) * s.sigma_ltd)


def reorder_point(s: Sku, ss: float) -> float:
    return s.d * s.lt + ss


def holding_cost(s: Sku, ss: float, rate: float = 0.25) -> float:
    return ss * s.unit_cost * rate


@dataclass
class CurvePoint:
    service: float
    units: float
    value: float          # inventory dollars in safety stock
    marginal: float       # extra dollars for this step vs the previous point


def tradeoff_curve(skus: list[Sku], levels: list[float]) -> list[CurvePoint]:
    out, prev = [], None
    for lvl in levels:
        units = sum(safety_stock_csl(s, lvl) for s in skus)
        value = sum(safety_stock_csl(s, lvl) * s.unit_cost for s in skus)
        out.append(CurvePoint(lvl, units, value, value - prev if prev is not None else 0.0))
        prev = value
    return out


def portfolio_value(skus: list[Sku], target: dict[str, float]) -> float:
    return sum(safety_stock_csl(s, target[s.abc]) * s.unit_cost for s in skus)
