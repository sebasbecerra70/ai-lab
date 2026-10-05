"""Warehouse geometry: slots, static travel cost, and order-pick route time."""
from __future__ import annotations

from dataclasses import dataclass

WALK_M_PER_S = 1.0
AISLE_PITCH_M = 3.0  # distance between aisle centerlines along the front cross-aisle
BAY_DEPTH_M = 1.2  # bay width along an aisle
LEVEL_PENALTY_S = {0: 2.0, 1: 0.0, 2: 3.0}  # floor = bend, 1 = golden zone, 2 = reach


@dataclass(frozen=True, order=True)
class Slot:
    aisle: int
    bay: int
    level: int

    @property
    def x(self) -> float:
        return self.aisle * AISLE_PITCH_M

    @property
    def y(self) -> float:
        return (self.bay + 0.5) * BAY_DEPTH_M

    def accepts(self, cube: str) -> bool:
        """Large items must live on the floor level."""
        return cube != "L" or self.level == 0


@dataclass
class Layout:
    aisles: int = 6
    bays: int = 10
    levels: int = 3

    def slots(self) -> list[Slot]:
        return [Slot(a, b, l) for a in range(self.aisles) for b in range(self.bays) for l in range(self.levels)]


def slot_cost(slot: Slot) -> float:
    """Seconds for a dedicated round trip from the depot to this slot, including handling."""
    return 2 * (slot.x + slot.y) / WALK_M_PER_S + LEVEL_PENALTY_S[slot.level]


def route_time(slots: list[Slot]) -> float:
    """Return-routing heuristic: walk the front cross-aisle to the farthest aisle with a pick,
    and enter each visited aisle only as deep as its deepest pick, then come back out."""
    if not slots:
        return 0.0
    cross = 2 * max(s.x for s in slots)
    deepest: dict[int, float] = {}
    for s in slots:
        deepest[s.aisle] = max(deepest.get(s.aisle, 0.0), s.y)
    in_aisle = sum(2 * y for y in deepest.values())
    handling = sum(LEVEL_PENALTY_S[s.level] for s in slots)
    return (cross + in_aisle) / WALK_M_PER_S + handling
