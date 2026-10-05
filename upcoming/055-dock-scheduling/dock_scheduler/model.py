"""Doors, trucks, and the schedule simulator that turns door sequences into wait, overtime and detention."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

CHECK_IN_MIN = 15        # paperwork, seal check, backing in
CHANGEOVER_MIN = 10      # pull out, sweep, next truck backs in
REEFER_WAIT_WEIGHT = 2.0  # a waiting reefer burns fuel and risks the cold chain
OVERTIME_WEIGHT = 5.0    # each minute past door close costs a crew overtime
DETENTION_WEIGHT = 10.0  # extra weight per minute a truck dwells past free time, so no single truck is sacrificed
FREE_DWELL_MIN = 120     # carriers bill detention after two hours on site
DETENTION_PER_HOUR = 75.0


def hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def clock(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass(frozen=True)
class Door:
    name: str
    reefer: bool
    min_per_pallet: float
    opens: int
    closes: int


@dataclass(frozen=True)
class Truck:
    name: str
    carrier: str
    arrival: int
    pallets: int
    reefer: bool


def load_doors(path: Path) -> list[Door]:
    with open(path) as f:
        return [Door(r["door"], r["reefer"] == "1", float(r["min_per_pallet"]), hhmm(r["opens"]), hhmm(r["closes"]))
                for r in csv.DictReader(f)]


def load_trucks(path: Path) -> list[Truck]:
    with open(path) as f:
        return [Truck(r["truck"], r["carrier"], hhmm(r["arrival"]), int(r["pallets"]), r["reefer"] == "1")
                for r in csv.DictReader(f)]


def compatible(truck: Truck, door: Door) -> bool:
    return door.reefer or not truck.reefer


def service_min(truck: Truck, door: Door) -> float:
    return CHECK_IN_MIN + truck.pallets * door.min_per_pallet


# A plan maps each door name to the ordered list of trucks it serves.
Plan = dict[str, list[Truck]]


@dataclass
class Slot:
    truck: Truck
    door: str
    start: float
    end: float

    @property
    def wait(self) -> float:
        return self.start - self.truck.arrival

    @property
    def over_free_dwell(self) -> float:
        return max(0.0, self.end - self.truck.arrival - FREE_DWELL_MIN)

    @property
    def detention(self) -> float:
        return self.over_free_dwell / 60 * DETENTION_PER_HOUR


def door_slots(seq: list[Truck], door: Door) -> list[Slot]:
    """A door works its queue in order: start = max(arrival, door free + changeover)."""
    slots = []
    free = float(door.opens)
    for i, t in enumerate(seq):
        if not compatible(t, door):
            raise ValueError(f"{t.name} needs a reefer door, {door.name} is dry")
        start = max(float(t.arrival), free + (CHANGEOVER_MIN if i else 0))
        free = start + service_min(t, door)
        slots.append(Slot(t, door.name, start, free))
    return slots


def simulate(plan: Plan, doors: dict[str, Door]) -> list[Slot]:
    slots = [s for name, seq in plan.items() for s in door_slots(seq, doors[name])]
    return sorted(slots, key=lambda s: (s.start, s.door))


def door_cost(seq: list[Truck], door: Door) -> float:
    """Objective for one door, in wait-minute units: weighted truck wait, plus a penalty for dwell past the
    free window (which makes cost convex in a single truck's wait), plus overtime past the door's close.
    Doors are independent, so local search only re-costs the doors a move touches."""
    slots = door_slots(seq, door)
    total = sum(s.wait * (REEFER_WAIT_WEIGHT if s.truck.reefer else 1.0) + DETENTION_WEIGHT * s.over_free_dwell
                for s in slots)
    if slots:
        total += OVERTIME_WEIGHT * max(0.0, slots[-1].end - door.closes)
    return total


def cost(plan: Plan, doors: dict[str, Door]) -> float:
    return sum(door_cost(seq, doors[name]) for name, seq in plan.items())


@dataclass
class Kpis:
    total_wait: float
    avg_wait: float
    max_wait: float
    reefer_avg_wait: float
    over_60: int
    detention: float
    overtime: float
    cost: float


def kpis(plan: Plan, doors: dict[str, Door]) -> Kpis:
    slots = simulate(plan, doors)
    waits = [s.wait for s in slots]
    last_end: dict[str, float] = {}
    for s in slots:
        last_end[s.door] = max(last_end.get(s.door, 0.0), s.end)
    overtime = sum(max(0.0, e - doors[d].closes) for d, e in last_end.items())
    cold = [s.wait for s in slots if s.truck.reefer] or [0.0]
    return Kpis(sum(waits), sum(waits) / len(waits), max(waits), sum(cold) / len(cold), sum(w > 60 for w in waits),
                sum(s.detention for s in slots), overtime, cost(plan, doors))
