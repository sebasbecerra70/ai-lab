import math
from pathlib import Path

import pytest

from routing import Problem, Stop, check, clarke_wright, dist, load_problem, nearest_neighbour, route_km, solve, two_opt

DATA = Path(__file__).resolve().parent.parent / "data" / "stops.csv"
DEPOT = Stop("DC", "depot", 0, 0, 0)


def s(id, x, y, d=1):
    return Stop(id, id, x, y, d)


def test_distance_applies_road_factor():
    assert dist(s("a", 0, 0), s("b", 3, 4)) == pytest.approx(5 * 1.3)


def test_oversized_stop_is_rejected_up_front():
    with pytest.raises(ValueError, match="exceed truck capacity"):
        Problem(DEPOT, (s("a", 1, 1, 9),), capacity=8)


def test_two_opt_uncrosses_a_route():
    # Square visited in a crossing order: (1,0) -> (0,1) -> (1,1) -> ... 2-opt should find the perimeter.
    route = [s("a", 1, 0), s("c", 0, 1), s("b", 1, 1)]
    better = two_opt(DEPOT, route)
    assert route_km(DEPOT, better) < route_km(DEPOT, route)
    assert route_km(DEPOT, better) == pytest.approx(4 * 1.3)


def test_two_opt_never_makes_a_route_longer():
    p = load_problem(DATA, 18)
    for r in nearest_neighbour(p):
        assert route_km(p.depot, two_opt(p.depot, r)) <= route_km(p.depot, r) + 1e-9


def test_savings_merges_stops_on_the_same_side():
    # Two clusters on opposite sides of the depot: savings should never pair across the depot.
    stops = (s("e1", 10, 0), s("e2", 11, 1), s("w1", -10, 0), s("w2", -11, -1))
    routes = clarke_wright(Problem(DEPOT, stops, capacity=2))
    assert sorted(sorted(x.id for x in r) for r in routes) == [["e1", "e2"], ["w1", "w2"]]


def test_capacity_forces_extra_trucks():
    stops = tuple(s(f"x{i}", 5 + i * 0.1, 5, 3) for i in range(4))
    assert len(clarke_wright(Problem(DEPOT, stops, capacity=6))) == 2
    assert len(clarke_wright(Problem(DEPOT, stops, capacity=12))) == 1


def test_route_length_limit_is_respected():
    p = load_problem(DATA, 40, max_route_km=80)
    sol = solve(p)
    assert check(p, sol) == []
    assert all(route_km(p.depot, list(r)) <= 80 for r in sol.routes)


@pytest.mark.parametrize("method", ["nearest", "nearest+2opt", "savings", "savings+2opt"])
def test_all_methods_are_feasible_on_sample(method):
    p = load_problem(DATA, 18, 110)
    sol = solve(p, method)
    assert check(p, sol) == []
    assert sol.trucks >= math.ceil(sum(x.demand for x in p.stops) / 18)


def test_savings_beats_the_hand_dispatch_baseline():
    p = load_problem(DATA, 18, 110)
    nn, cw = solve(p, "nearest"), solve(p, "savings+2opt")
    assert cw.km < nn.km * 0.85
    assert cw.cost(1.85, 240) < nn.cost(1.85, 240)


def test_check_reports_a_bad_solution():
    p = Problem(DEPOT, (s("a", 1, 1, 5), s("b", 2, 2, 5)), capacity=6)
    from routing import Solution
    bad = Solution("manual", ((p.stops[0], p.stops[1]),), 0.0, 1)
    assert check(p, bad) == ["route 1 over capacity: 10 > 6"]
