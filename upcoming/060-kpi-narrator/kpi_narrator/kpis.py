"""KPI table: variance to plan and prior period, favorable or not given each metric's direction, RAG status."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Kpi:
    metric: str
    unit: str          # usd | count | pct | hours | ratio | score
    direction: str     # up = higher is better, down = lower is better
    actual: float
    plan: float
    prior: float
    tolerance_pct: float
    owner: str


@dataclass(frozen=True)
class Variance:
    kpi: Kpi
    vs_plan: float
    vs_plan_pct: float
    vs_prior: float
    vs_prior_pct: float
    favorable: bool
    status: str        # green | amber | red

    @property
    def severity(self) -> float:
        """How far outside tolerance, in multiples of it: used to rank what the summary leads with."""
        tol = self.kpi.tolerance_pct or 1.0
        return abs(self.vs_plan_pct) / tol * (1 if not self.favorable else -1)


def load_kpis(path: Path) -> list[Kpi]:
    with open(path) as f:
        return [Kpi(r["metric"], r["unit"], r["direction"], float(r["actual"]), float(r["plan"]), float(r["prior"]),
                    float(r["tolerance_pct"]), r["owner"]) for r in csv.DictReader(f)]


def pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a - b) / abs(b) * 100


def variance(k: Kpi) -> Variance:
    """Green: favorable, or unfavorable within tolerance. Amber: up to twice the tolerance. Red: beyond.
    A zero tolerance (safety) makes any miss red."""
    vp = pct(k.actual, k.plan)
    sign = 1 if k.direction == "up" else -1
    favorable = sign * (k.actual - k.plan) >= 0
    miss = 0.0 if favorable else abs(vp)
    if not favorable and k.tolerance_pct == 0:
        status = "red"
    elif miss <= k.tolerance_pct:
        status = "green"
    elif miss <= 2 * k.tolerance_pct:
        status = "amber"
    else:
        status = "red"
    return Variance(k, k.actual - k.plan, vp, k.actual - k.prior, pct(k.actual, k.prior), favorable, status)


def fmt(value: float, unit: str, signed: bool = False) -> str:
    """The one place numbers are formatted, so the narrative check knows exactly how facts look."""
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    v = abs(value)
    if unit == "usd":
        if v >= 1e6:
            return f"{sign}${v / 1e6:.2f}M"
        if v >= 1e3:
            return f"{sign}${v / 1e3:.0f}k"
        return f"{sign}${v:.2f}"
    if unit == "pct":
        return f"{sign}{v:.1f}{' pp' if signed else '%'}"
    if unit == "hours":
        return f"{sign}{v:.1f} h"
    if unit == "count":
        return f"{sign}{v:,.0f}"
    return f"{sign}{v:.1f}" if unit == "ratio" else f"{sign}{v:.0f}"
