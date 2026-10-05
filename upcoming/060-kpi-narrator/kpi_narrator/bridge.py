"""Revenue bridge from plan to actual: volume, mix and price effects (the standard FP&A decomposition)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    name: str
    plan_units: float
    plan_price: float
    actual_units: float
    actual_price: float


@dataclass(frozen=True)
class Bridge:
    plan: float
    volume: float
    mix: float
    price: float
    actual: float
    by_segment: dict[str, dict[str, float]]


def load_segments(path: Path) -> list[Segment]:
    with open(path) as f:
        return [Segment(r["segment"], float(r["plan_units"]), float(r["plan_price"]), float(r["actual_units"]),
                        float(r["actual_price"])) for r in csv.DictReader(f)]


def bridge(segments: list[Segment]) -> Bridge:
    """volume = change in total units at the plan average price
    mix    = shift between segments at plan prices
    price  = actual units x change in price
    The three add up exactly to actual - plan."""
    plan_units = sum(s.plan_units for s in segments)
    act_units = sum(s.actual_units for s in segments)
    plan_rev = sum(s.plan_units * s.plan_price for s in segments)
    act_rev = sum(s.actual_units * s.actual_price for s in segments)
    by = {}
    for s in segments:
        share = s.plan_units / plan_units
        by[s.name] = {
            "volume": (act_units - plan_units) * share * s.plan_price,
            "mix": (s.actual_units - act_units * share) * s.plan_price,
            "price": s.actual_units * (s.actual_price - s.plan_price),
        }
    tot = {k: sum(v[k] for v in by.values()) for k in ("volume", "mix", "price")}
    return Bridge(plan_rev, tot["volume"], tot["mix"], tot["price"], act_rev, by)
