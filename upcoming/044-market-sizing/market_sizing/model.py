"""TAM / SAM / SOM, two ways: top-down from analyst spend, bottom-up from facility counts and price."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Assumption:
    name: str
    base: float
    low: float
    high: float
    unit: str
    source: str


@dataclass(frozen=True)
class Segment:
    region: str
    tier: str
    facilities: int
    racks_per_site: int
    fit: float  # share of facilities with the problem we solve (enough density/churn to need planning)


@dataclass
class Sizing:
    tam: float
    sam: float
    som: float
    som_binding: str = ""  # which constraint caps SOM: "sales capacity" or "market share"


@dataclass
class Market:
    product: str
    assumptions: dict[str, Assumption]
    segments: list[Segment]
    served_regions: set[str]
    served_tiers: set[str]

    def values(self, overrides: dict[str, float] | None = None) -> dict[str, float]:
        v = {k: a.base for k, a in self.assumptions.items()}
        v.update(overrides or {})
        return v


def load(folder: Path) -> Market:
    cfg = json.loads((folder / "assumptions.json").read_text())
    assumptions = {k: Assumption(k, **v) for k, v in cfg["assumptions"].items()}
    for a in assumptions.values():
        if not a.low <= a.base <= a.high:
            raise ValueError(f"{a.name}: base {a.base} outside [{a.low}, {a.high}]")
    with open(folder / "segments.csv") as f:
        segments = [Segment(r["region"], r["tier"], int(r["facilities"]), int(r["racks_per_site"]), float(r["fit"]))
                    for r in csv.DictReader(f)]
    return Market(cfg["product"], assumptions, segments, set(cfg["served_regions"]), set(cfg["served_tiers"]))


def top_down(m: Market, overrides: dict[str, float] | None = None) -> Sizing:
    v = m.values(overrides)
    tam = v["global_dcim_spend"] * v["capacity_planning_share"]
    sam = tam * v["served_region_share"] * v["served_tier_share"]
    return Sizing(tam, sam, *_som(sam, v))


def segment_value(s: Segment, price: float) -> float:
    return s.facilities * s.fit * s.racks_per_site * price


def bottom_up(m: Market, overrides: dict[str, float] | None = None) -> Sizing:
    v = m.values(overrides)
    price = v["price_per_rack"]
    tam = sum(segment_value(s, price) for s in m.segments)
    sam = sum(segment_value(s, price) for s in m.segments
              if s.region in m.served_regions and s.tier in m.served_tiers)
    return Sizing(tam, sam, *_som(sam, v, _avg_deal(m, price)))


def _avg_deal(m: Market, price: float) -> float:
    """Average annual contract value in the served segments, weighted by number of fitting facilities."""
    served = [s for s in m.segments if s.region in m.served_regions and s.tier in m.served_tiers]
    sites = sum(s.facilities * s.fit for s in served)
    return sum(segment_value(s, price) for s in served) / sites


def _som(sam: float, v: dict[str, float], avg_deal: float | None = None) -> tuple[float, str]:
    """SOM (ARR at the end of the horizon) = min(what the sales team can close, what the market
    will let a new entrant take). Ignores churn, which is small next to the ramp in years 1-3."""
    share_cap = sam * v["max_share_of_sam"]
    if avg_deal is None:  # top-down has no facility data, so deal size is its own assumption
        avg_deal = v["racks_per_deal"] * v["price_per_rack"]
    capacity = v["reps"] * v["deals_per_rep_per_year"] * v["years"] * avg_deal
    return (capacity, "sales capacity") if capacity < share_cap else (share_cap, "market share")


def reconcile(td: Sizing, bu: Sizing, tolerance: float = 0.30) -> dict:
    """Two independent estimates should land within ~30%; if not, one of the assumption sets is wrong."""
    out = {}
    for level in ("tam", "sam"):
        a, b = getattr(td, level), getattr(bu, level)
        gap = abs(a - b) / max(a, b)
        out[level] = {"top_down": a, "bottom_up": b, "gap": gap, "ok": gap <= tolerance}
    return out
