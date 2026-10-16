from pathlib import Path

import pytest

from rack_placement import Placer, Rack, Server, dominant_size, evaluate, load_racks, load_servers, validate

DATA = Path(__file__).resolve().parent.parent / "data"


def rack(id, row="R1", u=10, kw=5.0, used_u=0, used_kw=0.0):
    return Rack(id, row, u, kw, used_u, used_kw)


@pytest.fixture(scope="module")
def fleet():
    return load_racks(DATA / "racks.csv"), load_servers(DATA / "servers.csv")


def test_dominant_size_uses_the_scarcer_resource():
    assert dominant_size(Server("g", "gpu", 4, 3.4), 38, 8.6) == pytest.approx(3.4 / 8.6)
    assert dominant_size(Server("s", "jbod", 4, 0.2), 10, 8.6) == pytest.approx(0.4)


def test_power_budget_is_enforced_even_when_space_is_free():
    placer = Placer([rack("A", kw=4.0), rack("B", kw=4.0)], [Server("g1", "gpu", 2, 3.0), Server("g2", "gpu", 2, 3.0)])
    plan = placer.place("first_fit")
    assert {plan.rack_of("g1").id, plan.rack_of("g2").id} == {"A", "B"}


def test_anti_affinity_keeps_replicas_in_different_racks():
    servers = [Server(f"w{i}", "web", 1, 0.3, "web") for i in range(3)]
    plan = Placer([rack("A"), rack("B"), rack("C")], servers).place("best_fit")
    assert len({plan.rack_of(s.id).id for s in servers}) == 3


def test_row_spread_caps_replicas_per_row():
    racks = [rack("A1", "R1"), rack("A2", "R1"), rack("B1", "R2"), rack("B2", "R2")]
    servers = [Server(f"db{i}", "db", 1, 0.5, "db") for i in range(2)]
    plan = Placer(racks, servers).place("first_fit")
    assert {plan.rack_of("db0").row, plan.rack_of("db1").row} == {"R1", "R2"}


def test_unplaceable_server_is_reported_with_the_binding_constraint():
    plan = Placer([rack("A", kw=2.0)], [Server("big", "gpu", 4, 3.4)]).place("best_fit")
    assert [(s.id, why) for s, why in plan.unplaced] == [("big", "power")]


def test_best_fit_prefers_powered_racks_over_opening_empty_ones():
    racks = [rack("empty"), rack("brown", used_u=4, used_kw=1.0)]
    plan = Placer(racks, [Server("x", "web", 1, 0.4)]).place("best_fit")
    assert plan.rack_of("x").id == "brown"


def test_consolidation_drains_a_lightly_used_rack():
    racks = [rack("A", u=4), rack("B", u=4)]
    servers = [Server("a", "web", 2, 0.5), Server("b", "web", 1, 0.5)]
    placer = Placer(racks, servers)
    # Worst fit spreads, then the drain pass should pack everything into one rack.
    plan = placer.place("worst_fit", consolidate=False)
    assert evaluate(plan, servers).racks_used == 2
    assert placer.consolidate(plan) == 1
    assert evaluate(plan, servers).racks_used == 1


def test_failed_drain_rolls_back_without_losing_servers():
    racks = [rack("A", u=2), rack("B", u=2)]
    servers = [Server("a", "web", 2, 0.5), Server("b", "web", 2, 0.5)]
    placer = Placer(racks, servers)
    plan = placer.place("best_fit", consolidate=True)
    assert sorted(s.id for r in plan.racks for s in r.servers) == ["a", "b"]


def test_input_racks_are_not_mutated(fleet):
    racks, servers = fleet
    Placer(racks, servers).place("best_fit")
    assert all(not r.servers for r in racks)


@pytest.mark.parametrize("strategy", ["first_fit", "best_fit", "worst_fit"])
def test_sample_fleet_plans_are_valid_and_complete(fleet, strategy):
    racks, servers = fleet
    placer = Placer(racks, servers)
    plan = placer.place(strategy)
    assert validate(plan, placer) == []
    assert not plan.unplaced
    assert sorted(s.id for r in plan.racks for s in r.servers) == sorted(s.id for s in servers)


def test_drain_beats_plain_packing_and_respects_lower_bound(fleet):
    racks, servers = fleet
    placer = Placer(racks, servers)
    plain = evaluate(placer.place("best_fit", consolidate=False), servers)
    drained = evaluate(placer.place("best_fit"), servers)
    assert drained.racks_used < plain.racks_used
    assert drained.racks_used >= drained.lower_bound_racks == 8  # ceph-prod has 8 replicas


def test_validate_catches_hand_made_violations():
    a = rack("A", u=2, kw=1.0)
    placer = Placer([a], [Server("x", "web", 1, 0.6, "g"), Server("y", "web", 2, 0.6, "g")])
    plan = placer.place("first_fit", consolidate=False)
    plan.racks[0].servers = [Server("x", "web", 1, 0.6, "g"), Server("y", "web", 2, 0.6, "g")]
    problems = validate(plan, placer)
    assert any("over U" in p for p in problems)
    assert any("over power" in p for p in problems)
    assert any("sharing the rack" in p for p in problems)
