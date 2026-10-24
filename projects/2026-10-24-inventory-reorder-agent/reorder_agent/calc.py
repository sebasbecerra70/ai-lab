"""Inventory math: safety stock, reorder point and economic order quantity."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

DAYS_PER_YEAR = 365


def z_for_service_level(p: float) -> float:
    """Inverse normal CDF by bisection on erf; plenty accurate for service levels."""
    if not 0.5 <= p < 1:
        raise ValueError("service level must be in [0.5, 1)")
    lo, hi = 0.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class Item:
    sku: str
    description: str
    supplier: str
    unit_cost: float
    on_hand: int
    on_order: int
    daily_demand: float
    demand_std: float
    lead_time_days: float
    lead_time_std: float
    order_cost: float  # cost to place one PO line (admin, receiving)
    holding_rate: float  # annual carrying cost as a share of unit cost
    case_pack: int
    service_level: float

    @property
    def position(self) -> int:
        return self.on_hand + self.on_order


def load_items(path: Path) -> list[Item]:
    with open(path, newline="") as f:
        return [
            Item(r["sku"], r["description"], r["supplier"], float(r["unit_cost"]), int(r["on_hand"]), int(r["on_order"]),
                 float(r["daily_demand"]), float(r["demand_std"]), float(r["lead_time_days"]), float(r["lead_time_std"]),
                 float(r["order_cost"]), float(r["holding_rate"]), int(r["case_pack"]), float(r["service_level"]))
            for r in csv.DictReader(f)
        ]


def safety_stock(it: Item) -> float:
    """Covers both demand variability during lead time and lead-time variability."""
    z = z_for_service_level(it.service_level)
    return z * math.sqrt(it.lead_time_days * it.demand_std ** 2 + it.daily_demand ** 2 * it.lead_time_std ** 2)


def reorder_point(it: Item) -> float:
    return it.daily_demand * it.lead_time_days + safety_stock(it)


def eoq(it: Item) -> float:
    annual = it.daily_demand * DAYS_PER_YEAR
    holding = it.unit_cost * it.holding_rate
    return math.sqrt(2 * annual * it.order_cost / holding)


def round_to_pack(qty: float, pack: int) -> int:
    return max(pack, math.ceil(qty / pack) * pack)


def annual_cost(it: Item, q: float) -> float:
    """Ordering + holding cost per year for order size q (the EOQ objective)."""
    annual = it.daily_demand * DAYS_PER_YEAR
    return annual / q * it.order_cost + q / 2 * it.unit_cost * it.holding_rate
