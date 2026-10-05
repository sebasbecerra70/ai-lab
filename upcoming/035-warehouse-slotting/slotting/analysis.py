"""Load data, compute pick velocity and ABC classes."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .layout import Slot


@dataclass(frozen=True)
class Sku:
    sku: str
    description: str
    cube: str  # S, M, L


def load_skus(path: Path) -> dict[str, Sku]:
    with open(path, newline="") as f:
        return {r["sku"]: Sku(r["sku"], r["description"], r["cube"]) for r in csv.DictReader(f)}


def load_orders(path: Path) -> dict[str, list[str]]:
    orders: dict[str, list[str]] = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            orders[r["order_id"]].append(r["sku"])
    return dict(orders)


def load_slotting(path: Path) -> dict[str, Slot]:
    with open(path, newline="") as f:
        return {r["sku"]: Slot(int(r["aisle"]), int(r["bay"]), int(r["level"])) for r in csv.DictReader(f)}


def pick_velocity(orders: dict[str, list[str]], skus: dict[str, Sku]) -> Counter:
    """Pick lines per SKU. Lines, not units, drive travel: one visit per line."""
    v = Counter({s: 0 for s in skus})
    for lines in orders.values():
        v.update(lines)
    return v


def abc_classes(velocity: Counter, a_cut: float = 0.80, b_cut: float = 0.95) -> dict[str, str]:
    """Pareto classes by cumulative share of pick lines."""
    total = sum(velocity.values()) or 1
    out, cum = {}, 0.0
    for sku, picks in sorted(velocity.items(), key=lambda kv: (-kv[1], kv[0])):
        cls = "A" if cum < a_cut else "B" if cum < b_cut else "C"
        out[sku] = cls
        cum += picks / total
    return out


def abc_summary(velocity: Counter, classes: dict[str, str]) -> dict[str, tuple[int, float]]:
    total = sum(velocity.values()) or 1
    res = {}
    for cls in "ABC":
        members = [s for s, c in classes.items() if c == cls]
        res[cls] = (len(members), sum(velocity[s] for s in members) / total)
    return res
