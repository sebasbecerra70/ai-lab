from collections import Counter
from pathlib import Path

import pytest

from slotting import (Layout, Sku, Slot, SlottingError, abc_classes, apply_top_moves, assign_slots, evaluate,
                      load_orders, load_skus, load_slotting, pick_velocity, prioritized_moves, route_time,
                      slot_cost, validate)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def sample():
    skus, orders = load_skus(DATA / "skus.csv"), load_orders(DATA / "order_lines.csv")
    return skus, orders, load_slotting(DATA / "current_slots.csv"), pick_velocity(orders, skus)


def test_slot_cost_prefers_close_golden_zone():
    assert slot_cost(Slot(0, 0, 1)) < slot_cost(Slot(0, 0, 0)) < slot_cost(Slot(0, 0, 2))
    assert slot_cost(Slot(0, 0, 1)) < slot_cost(Slot(3, 0, 1)) < slot_cost(Slot(3, 9, 1))


def test_route_time_uses_return_routing():
    # one aisle, two picks: walk to the deepest one only
    one = route_time([Slot(0, 4, 1), Slot(0, 1, 1)])
    assert one == pytest.approx(2 * 5.4)
    # aisle 2 adds the cross-aisle walk 2 * 6m
    assert route_time([Slot(2, 0, 1)]) == pytest.approx(12 + 1.2)
    assert route_time([]) == 0


def test_abc_classes_follow_pareto_cuts():
    v = Counter({"a": 70, "b": 15, "c": 10, "d": 5})
    assert abc_classes(v) == {"a": "A", "b": "A", "c": "B", "d": "C"}


def test_velocity_counts_lines_not_units(sample):
    skus, orders, _, velocity = sample
    assert sum(velocity.values()) == sum(len(v) for v in orders.values())
    assert set(velocity) == set(skus)


def test_fastest_mover_gets_best_slot(sample):
    skus, _, _, velocity = sample
    target = assign_slots(skus, velocity, Layout())
    top = velocity.most_common(1)[0][0]
    best = min(Layout().slots(), key=slot_cost)
    assert target[top] == best or skus[top].cube == "L"


def test_assignment_respects_cube_and_uniqueness(sample):
    skus, _, current, velocity = sample
    target = assign_slots(skus, velocity, Layout())
    assert validate(target, skus) == [] and validate(current, skus) == []
    assert all(target[s].level == 0 for s in skus if skus[s].cube == "L")


def test_validate_catches_bad_slotting():
    skus = {"x": Sku("x", "", "L"), "y": Sku("y", "", "S")}
    problems = validate({"x": Slot(0, 0, 2), "y": Slot(0, 0, 2)}, skus)
    assert len(problems) == 2


def test_not_enough_compatible_slots_raises():
    skus = {f"L{i}": Sku(f"L{i}", "", "L") for i in range(3)}
    with pytest.raises(SlottingError):
        assign_slots(skus, Counter(), Layout(aisles=1, bays=2, levels=3))


def test_optimized_slotting_cuts_travel(sample):
    skus, orders, current, velocity = sample
    before, after = evaluate(orders, current), evaluate(orders, assign_slots(skus, velocity, Layout()))
    assert after.total_hours < before.total_hours * 0.6


def test_phased_moves_give_diminishing_returns(sample):
    skus, orders, current, velocity = sample
    moves = prioritized_moves(current, assign_slots(skus, velocity, Layout()), velocity)
    assert moves == sorted(moves, key=lambda m: -m.est_seconds_saved)
    hours = [evaluate(orders, apply_top_moves(current, moves, k)).total_hours for k in (0, 5, 10, 20)]
    assert hours[0] > hours[1] > hours[2] > hours[3]
    assert (hours[0] - hours[1]) > (hours[2] - hours[3]) / 2
    phased = apply_top_moves(current, moves, 10)
    assert len(set(phased.values())) == len(phased)
