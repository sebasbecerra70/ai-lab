"""Velocity-based slot assignment and before/after evaluation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .analysis import Sku
from .layout import Layout, Slot, route_time, slot_cost


class SlottingError(RuntimeError):
    pass


def assign_slots(skus: dict[str, Sku], velocity: Counter, layout: Layout) -> dict[str, Slot]:
    """Greedy: the fastest movers take the cheapest compatible slots.

    Sorting both lists and matching in order is optimal for a single-command
    (one-line) picking model when all slots fit all SKUs; the cube constraint
    makes it a heuristic, which we handle by letting each SKU take its best
    compatible free slot.
    """
    free = sorted(layout.slots(), key=lambda s: (slot_cost(s), s))
    out: dict[str, Slot] = {}
    for sku in sorted(skus, key=lambda s: (-velocity[s], s)):
        for i, slot in enumerate(free):
            if slot.accepts(skus[sku].cube):
                out[sku] = free.pop(i)
                break
        else:
            raise SlottingError(f"no compatible slot left for {sku} ({skus[sku].cube})")
    return out


def validate(slotting: dict[str, Slot], skus: dict[str, Sku]) -> list[str]:
    problems = []
    if len(set(slotting.values())) != len(slotting):
        problems.append("two SKUs share a slot")
    problems += [f"{s} ({skus[s].cube}) not allowed at level {slot.level}"
                 for s, slot in slotting.items() if not slot.accepts(skus[s].cube)]
    return problems


@dataclass
class TravelReport:
    total_hours: float
    sec_per_order: float
    sec_per_line: float


def evaluate(orders: dict[str, list[str]], slotting: dict[str, Slot]) -> TravelReport:
    total = sum(route_time([slotting[s] for s in lines]) for lines in orders.values())
    n_lines = sum(len(lines) for lines in orders.values())
    return TravelReport(total / 3600, total / len(orders), total / n_lines)


@dataclass
class Move:
    sku: str
    old: Slot
    new: Slot
    est_seconds_saved: float


def prioritized_moves(current: dict[str, Slot], target: dict[str, Slot], velocity: Counter) -> list[Move]:
    """Rank moves by estimated savings (picks x single-command slot cost delta).

    Re-slotting costs labor, so most sites do the top moves first. The estimate
    ignores interactions between moves, which is fine for prioritizing.
    """
    moves = [Move(s, current[s], target[s], velocity[s] * (slot_cost(current[s]) - slot_cost(target[s])))
             for s in target if current[s] != target[s]]
    return sorted(moves, key=lambda m: -m.est_seconds_saved)


def apply_top_moves(current: dict[str, Slot], moves: list[Move], k: int) -> dict[str, Slot]:
    """Apply the top-k moves; SKUs displaced from a target slot swap into the mover's old slot."""
    result = dict(current)
    for m in moves[:k]:
        occupant = next((s for s, sl in result.items() if sl == m.new and s != m.sku), None)
        if occupant:
            result[occupant] = result[m.sku]
        result[m.sku] = m.new
    return result
