import itertools
from pathlib import Path

import pytest

from dock_scheduler import (Door, Truck, cost, descend, door_slots, greedy, kpis, load_doors, load_trucks,
                            local_search, rotation, simulate)
from dock_scheduler.model import CHANGEOVER_MIN, CHECK_IN_MIN

DATA = Path(__file__).resolve().parent.parent / "data"
DRY = Door("A", False, 1.0, 360, 900)
COLD = Door("R", True, 1.0, 360, 900)


def truck(name, arrival, pallets=20, reefer=False):
    return Truck(name, "X", arrival, pallets, reefer)


def all_trucks(plan):
    return sorted(t.name for seq in plan.values() for t in seq)


def test_door_works_queue_with_changeover_and_waits():
    a, b = truck("a", 360, 20), truck("b", 365, 10)
    s1, s2 = door_slots([a, b], DRY)
    assert (s1.start, s1.end) == (360, 360 + CHECK_IN_MIN + 20)
    assert s2.start == s1.end + CHANGEOVER_MIN and s2.wait == s2.start - 365
    # a truck that arrives after the door is free starts on arrival
    assert door_slots([truck("c", 600)], DRY)[0].wait == 0


def test_reefer_truck_on_dry_door_is_rejected():
    with pytest.raises(ValueError):
        simulate({"A": [truck("r", 360, reefer=True)]}, {"A": DRY})


def test_reefer_wait_costs_double():
    doors = {"A": COLD}
    dry = cost({"A": [truck("a", 360), truck("b", 360)]}, doors)
    cold = cost({"A": [truck("a", 360), truck("b", 360, reefer=True)]}, doors)
    assert cold == pytest.approx(2 * dry)


def test_overtime_past_close_is_penalized():
    late = Door("L", False, 1.0, 360, 400)
    k = kpis({"L": [truck("a", 380, 20)]}, {"L": late})
    assert k.overtime == pytest.approx(380 + CHECK_IN_MIN + 20 - 400)
    assert k.cost == pytest.approx(5.0 * k.overtime)


def test_greedy_respects_reefer_doors_and_keeps_them_for_reefers():
    trucks = [truck("d1", 360), truck("r1", 361, reefer=True), truck("d2", 362)]
    plan = greedy(trucks, [COLD, DRY])
    assert [t.name for t in plan["R"]] == ["r1"]
    assert all(not t.reefer for t in plan["A"])


def test_every_plan_schedules_every_truck_exactly_once():
    doors, trucks = load_doors(DATA / "doors.csv"), load_trucks(DATA / "appointments.csv")
    names = sorted(t.name for t in trucks)
    best, _ = local_search(greedy(trucks, doors), doors, kicks=3)
    for plan in (rotation(trucks, doors), greedy(trucks, doors), best):
        assert all_trucks(plan) == names


def test_descent_is_monotone_and_never_worse_than_its_start():
    doors, trucks = load_doors(DATA / "doors.csv"), load_trucks(DATA / "appointments.csv")
    by_name = {d.name: d for d in doors}
    start = rotation(trucks, doors)
    plan, history = descend(start, by_name)
    assert all(b < a for a, b in zip(history, history[1:]))
    assert cost(plan, by_name) == pytest.approx(history[-1]) and history[-1] < cost(start, by_name)


def test_local_search_finds_the_brute_force_optimum_on_a_small_instance():
    doors = [COLD, Door("B", False, 1.5, 360, 900)]
    trucks = [truck("a", 360, 24), truck("b", 365, 8, True), truck("c", 370, 16), truck("d", 372, 20, True),
              truck("e", 380, 10)]
    by_name = {d.name: d for d in doors}
    best = float("inf")
    for assign in itertools.product("RB", repeat=len(trucks)):
        groups = {"R": [t for t, d in zip(trucks, assign) if d == "R"], "B": [t for t, d in zip(trucks, assign) if d == "B"]}
        if any(t.reefer for t in groups["B"]):
            continue
        for pr in itertools.permutations(groups["R"]):
            for pb in itertools.permutations(groups["B"]):
                best = min(best, cost({"R": list(pr), "B": list(pb)}, by_name))
    plan, _ = local_search(greedy(trucks, doors), doors, kicks=20)
    assert cost(plan, by_name) == pytest.approx(best)


def test_sample_day_ranking_rotation_worst_local_search_best():
    doors, trucks = load_doors(DATA / "doors.csv"), load_trucks(DATA / "appointments.csv")
    by_name = {d.name: d for d in doors}
    g = greedy(trucks, doors)
    ls, _ = local_search(g, doors, kicks=5)
    r, gk, lk = (kpis(p, by_name) for p in (rotation(trucks, doors), g, ls))
    assert r.cost > gk.cost >= lk.cost
    assert r.avg_wait > 2 * gk.avg_wait
    assert lk.detention < r.detention


def test_local_search_is_deterministic_for_a_seed():
    doors, trucks = load_doors(DATA / "doors.csv"), load_trucks(DATA / "appointments.csv")
    g = greedy(trucks, doors)
    assert local_search(g, doors, kicks=3, seed=1)[1] == local_search(g, doors, kicks=3, seed=1)[1]
