"""Server cohorts, cost assumptions, and the per-year TCO of keeping or replacing a cohort."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

HOURS_PER_YEAR = 8760


@dataclass(frozen=True)
class Platform:
    name: str
    available_year: int
    perf: float
    watts: float
    price: float
    warranty_years: int


@dataclass(frozen=True)
class Cohort:
    """A group of identical servers bought together. `perf` is per server, in a common benchmark unit."""
    name: str
    role: str
    servers: int
    age: int
    gen: str
    perf: float
    watts: float
    warranty_years: int

    @property
    def capacity(self) -> float:
        return self.servers * self.perf


@dataclass(frozen=True)
class Assumptions:
    horizon_years: int
    annual_budget: list[float]
    discount_rate: float
    window_years: int
    end_of_support_age: int
    power_price_kwh: float
    pue: float
    license_per_server: float
    space_network_per_server: float
    maintenance_post_warranty: float
    maintenance_escalation: float
    afr_base: float
    afr_growth: float
    afr_wearout_age: int
    cost_per_failure: float
    migration_per_old_server: float
    salvage_per_old_server: float
    platforms: list[Platform] = field(default_factory=list)


def load_fleet(path: Path) -> list[Cohort]:
    with open(path) as f:
        return [Cohort(r["cohort"], r["role"], int(r["servers"]), int(r["age"]), r["gen"], float(r["perf"]),
                       float(r["watts"]), int(r["warranty_years"])) for r in csv.DictReader(f)]


def load_assumptions(path: Path) -> Assumptions:
    raw = json.loads(path.read_text())
    raw["platforms"] = [Platform(**p) for p in raw["platforms"]]
    return Assumptions(**raw)


def afr(age: int, a: Assumptions) -> float:
    """Annual failure rate: flat while young, then compounding wear-out (the right side of the bathtub)."""
    return min(1.0, a.afr_base * (1 + a.afr_growth) ** max(0, age - a.afr_wearout_age))


def server_opex(age: int, watts: float, warranty_years: int, a: Assumptions) -> dict[str, float]:
    """Annual run cost of one server at a given age, by component."""
    past = age - warranty_years
    return {
        "energy": watts / 1000 * HOURS_PER_YEAR * a.pue * a.power_price_kwh,
        "license": a.license_per_server,
        "space": a.space_network_per_server,
        "maintenance": a.maintenance_post_warranty * (1 + a.maintenance_escalation) ** past if past >= 0 else 0.0,
        "failures": afr(age, a) * a.cost_per_failure,
    }


def cohort_opex(c: Cohort, a: Assumptions, years_ahead: int = 0) -> float:
    return c.servers * sum(server_opex(c.age + years_ahead, c.watts, c.warranty_years, a).values())


def platform_for(year: int, a: Assumptions) -> Platform:
    """The newest platform available in a given plan year."""
    avail = [p for p in a.platforms if p.available_year <= year]
    if not avail:
        raise ValueError(f"no platform available in year {year}")
    return max(avail, key=lambda p: p.available_year)


def replacement(c: Cohort, p: Platform, year: int) -> Cohort:
    """Like-for-like capacity on the new platform: fewer, faster servers (the consolidation ratio)."""
    n = math.ceil(c.capacity / p.perf - 1e-9)
    return Cohort(f"{c.name}>{p.name}@y{year + 1}", c.role, n, 0, p.name, p.perf, p.watts, p.warranty_years)


def refresh_capex(c: Cohort, p: Platform, a: Assumptions) -> float:
    new = replacement(c, p, 0)
    return new.servers * p.price + c.servers * (a.migration_per_old_server - a.salvage_per_old_server)


def window_cost(c: Cohort, year: int, refresh_at: int | None, a: Assumptions) -> float:
    """Present value at `year` of running this capacity for `window_years`: keep the old servers until
    `refresh_at` (None = never), then pay capex and run the newest platform available at that point."""
    total = 0.0
    new = None
    for t in range(a.window_years):
        y = year + t
        disc = (1 + a.discount_rate) ** -t
        if refresh_at is not None and y == refresh_at:
            p = platform_for(y, a)
            total += refresh_capex(replace(c, age=c.age + t), p, a) * disc
            new = replacement(c, p, y)
            new_start = t
        if new is None:
            total += cohort_opex(c, a, t) * disc
        else:
            total += cohort_opex(new, a, t - new_start) * disc
    return total


def npv_of_refresh(c: Cohort, year: int, a: Assumptions, delay: int = 0) -> float:
    """Savings over the window from refreshing in `year + delay` instead of keeping the cohort."""
    return window_cost(c, year, None, a) - window_cost(c, year, year + delay, a)
