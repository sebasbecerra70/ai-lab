"""Capacity model: per-hall power/cooling/space headroom, site PUE, and a monthly growth forecast."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Hall:
    name: str
    power_capacity_kw: float
    it_load_kw: float
    cooling_capacity_kw: float
    cooling_load_kw: float
    rack_positions: int
    racks_installed: float
    kw_per_rack_design: float

    @property
    def cooling_ratio(self) -> float:
        """Heat rejected per kW of IT. New load is assumed to bring cooling demand at the same ratio."""
        return self.cooling_load_kw / self.it_load_kw if self.it_load_kw else 1.0


@dataclass(frozen=True)
class Site:
    facility_overhead_kw: float
    chiller_cop: float
    utility_feed_kw: float
    safety_margin: float = 0.9


@dataclass(frozen=True)
class StepLoad:
    month: int
    hall: str
    kw: float
    racks: int


@dataclass(frozen=True)
class Scenario:
    name: str
    monthly_growth: float
    step_loads: tuple[StepLoad, ...] = ()


@dataclass
class Headroom:
    hall: str
    power_kw: float
    cooling_kw: float
    racks: float
    binding: str  # the constraint with the highest utilization of usable capacity
    utilization: dict[str, float] = field(default_factory=dict)


def load_halls(path: str | Path) -> list[Hall]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    halls = []
    for r in rows:
        hall = Hall(r["hall"], float(r["power_capacity_kw"]), float(r["it_load_kw"]),
                    float(r["cooling_capacity_kw"]), float(r["cooling_load_kw"]),
                    int(r["rack_positions"]), float(r["racks_installed"]), float(r["kw_per_rack_design"]))
        if hall.it_load_kw < 0 or hall.power_capacity_kw <= 0:
            raise ValueError(f"hall {hall.name}: capacities must be positive")
        halls.append(hall)
    return halls


def load_site(path: str | Path) -> Site:
    return Site(**json.loads(Path(path).read_text()))


def load_scenarios(path: str | Path) -> list[Scenario]:
    raw = json.loads(Path(path).read_text())
    return [Scenario(name, s["monthly_growth"], tuple(StepLoad(**x) for x in s.get("step_loads", [])))
            for name, s in raw.items()]


def headroom(hall: Hall, margin: float) -> Headroom:
    """Headroom against usable capacity (design × margin), not nameplate. Nobody runs a hall at 100%."""
    usable = {
        "power": hall.power_capacity_kw * margin,
        "cooling": hall.cooling_capacity_kw * margin,
        "space": hall.rack_positions * margin,
    }
    used = {"power": hall.it_load_kw, "cooling": hall.cooling_load_kw, "space": hall.racks_installed}
    util = {k: used[k] / usable[k] for k in usable}
    binding = max(util, key=util.get)
    return Headroom(hall.name, usable["power"] - used["power"], usable["cooling"] - used["cooling"],
                    usable["space"] - used["space"], binding, util)


def facility_load_kw(halls: list[Hall], site: Site) -> float:
    it = sum(h.it_load_kw for h in halls)
    cooling_electrical = sum(h.cooling_load_kw for h in halls) / site.chiller_cop
    return it + cooling_electrical + site.facility_overhead_kw


def pue(halls: list[Hall], site: Site) -> float:
    it = sum(h.it_load_kw for h in halls)
    if it <= 0:
        raise ValueError("PUE is undefined with zero IT load")
    return facility_load_kw(halls, site) / it


def months_to_exhaust(load: float, usable: float, monthly_growth: float) -> int | None:
    """Closed form for pure compound growth: the first month where load × (1+g)^m > usable."""
    if load > usable:
        return 0
    if monthly_growth <= 0 or load <= 0:
        return None
    m = math.log(usable / load) / math.log(1 + monthly_growth)
    return math.floor(m) + 1


def project(halls: list[Hall], scenario: Scenario, month: int) -> list[Hall]:
    """Hall state after `month` months: organic compound growth plus any step loads landed so far."""
    factor = (1 + scenario.monthly_growth) ** month
    out = []
    for h in halls:
        it, racks = h.it_load_kw * factor, h.racks_installed * factor
        for s in scenario.step_loads:
            if s.hall == h.name and s.month <= month:
                it += s.kw
                racks += s.racks
        out.append(replace(h, it_load_kw=it, racks_installed=racks, cooling_load_kw=it * h.cooling_ratio))
    return out


@dataclass
class Forecast:
    scenario: str
    exhaustion: dict[str, dict[str, int | None]]  # hall -> constraint -> month (None = beyond horizon)
    utility_month: int | None
    pue_by_year: list[float]

    def first_wall(self) -> tuple[str, str, int] | None:
        hits = [(m, hall, c) for hall, cs in self.exhaustion.items() for c, m in cs.items() if m is not None]
        if not hits:
            return None
        m, hall, c = min(hits)
        return hall, c, m


def forecast(halls: list[Hall], site: Site, scenario: Scenario, horizon: int = 60) -> Forecast:
    exhaustion: dict[str, dict[str, int | None]] = {h.name: {"power": None, "cooling": None, "space": None}
                                                    for h in halls}
    utility_month = None
    pues = []
    for m in range(horizon + 1):
        state = project(halls, scenario, m)
        for h in state:
            hr = headroom(h, site.safety_margin)
            for constraint, left in (("power", hr.power_kw), ("cooling", hr.cooling_kw), ("space", hr.racks)):
                if left < 0 and exhaustion[h.name][constraint] is None:
                    exhaustion[h.name][constraint] = m
        if utility_month is None and facility_load_kw(state, site) > site.utility_feed_kw * site.safety_margin:
            utility_month = m
        if m % 12 == 0:
            pues.append(round(pue(state, site), 3))
    return Forecast(scenario.name, exhaustion, utility_month, pues)
