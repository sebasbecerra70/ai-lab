import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from refresh_planner import (Cohort, Platform, afr, cohort_opex, knapsack, load_assumptions, load_fleet, mandatory,
                             npv_of_refresh, refresh_capex, replacement, run, server_opex, tranches, window_cost)
from refresh_planner.planner import TRANCHE, choose_tco

DATA = Path(__file__).resolve().parent.parent / "data"
A = load_assumptions(DATA / "assumptions.json")
FLEET = load_fleet(DATA / "fleet.csv")
OLD = Cohort("old", "web", 100, 6, "gen3", 60, 420, 5)


def test_failure_rate_is_flat_then_wears_out():
    assert afr(1, A) == afr(3, A) == A.afr_base
    assert afr(5, A) == pytest.approx(A.afr_base * (1 + A.afr_growth) ** 2)
    assert afr(40, A) == 1.0


def test_maintenance_is_free_in_warranty_and_escalates_after():
    assert server_opex(4, 400, 5, A)["maintenance"] == 0
    assert server_opex(5, 400, 5, A)["maintenance"] == A.maintenance_post_warranty
    assert server_opex(7, 400, 5, A)["maintenance"] == pytest.approx(A.maintenance_post_warranty * 1.15 ** 2)
    # 650 W around the clock at PUE 1.45 and $0.11/kWh
    assert server_opex(0, 650, 5, A)["energy"] == pytest.approx(0.65 * 8760 * 1.45 * 0.11)


def test_replacement_keeps_capacity_with_fewer_servers():
    p = A.platforms[0]
    new = replacement(OLD, p, 0)
    assert new.servers == 28  # ceil(100 * 60 / 220)
    assert new.capacity >= OLD.capacity and new.age == 0
    assert refresh_capex(OLD, p, A) == 28 * p.price + 100 * (A.migration_per_old_server - A.salvage_per_old_server)


def test_window_cost_without_refresh_is_discounted_opex():
    expected = sum(cohort_opex(OLD, A, t) / 1.08 ** t for t in range(A.window_years))
    assert window_cost(OLD, 0, None, A) == pytest.approx(expected)


def test_refresh_pays_for_old_gear_but_not_for_young_gear():
    assert npv_of_refresh(OLD, 0, A) > 0
    young = Cohort("young", "web", 100, 1, "gen6", 220, 640, 5)
    assert npv_of_refresh(young, 0, A) < 0


def test_waiting_for_next_generation_can_beat_refreshing_now():
    # gen7 lands in year 2; from year 1 a mid-life gen4 cohort is worth more refreshed a year later
    mid = Cohort("mid", "batch", 100, 5, "gen4", 100, 500, 5)
    assert npv_of_refresh(mid, 1, A, delay=1) > npv_of_refresh(mid, 1, A)
    picks, deferred = choose_tco([mid], 1, 5_000_000, A)
    assert picks == [] and deferred == ["mid"]
    # but not when waiting would collide with end of support
    picks, deferred = choose_tco([replace(mid, age=A.end_of_support_age - 2)], 1, 5_000_000, A)
    assert picks and not deferred


def test_knapsack_matches_brute_force_and_respects_budget():
    items = [("a", 40_000, 9), ("b", 30_000, 7), ("c", 50_000, 12), ("d", 20_000, 3), ("e", 10_000, -5)]
    budget = 90_000
    best = max((sum(v for _, _, v in combo), combo) for r in range(len(items) + 1)
               for combo in itertools.combinations(items, r) if sum(c for _, c, _ in combo) <= budget)
    picked = knapsack(items, budget)
    assert sum(v for k, _, v in items if k in picked) == best[0]
    assert sum(c for k, c, _ in items if k in picked) <= budget and "e" not in picked


def test_tranches_split_evenly_and_cover_the_cohort():
    parts = tranches(replace(OLD, servers=250))
    assert [t.servers for t in parts] == [84, 83, 83]
    assert all(t.servers <= TRANCHE for t in parts)


def test_every_policy_holds_capacity_and_retires_before_end_of_support():
    for policy in ("run-to-EOS", "5-year age", "TCO-optimized"):
        res = run(FLEET, A, policy)
        for role in {c.role for c in FLEET}:
            before = sum(c.capacity for c in FLEET if c.role == role)
            assert sum(c.capacity for c in res.exit_fleet if c.role == role) >= before
        # the exit fleet has aged one more year; nothing should have run a year past support
        assert all(c.age <= A.end_of_support_age for c in res.exit_fleet)


def test_mandatory_refreshes_happen_in_their_year():
    res = run(FLEET, A, "run-to-EOS")
    first = res.years[0]
    assert {x.cohort for x in first.actions} == {c.name for c in FLEET if mandatory(c, A)}
    assert all(x.reason == "end of support" for y in res.years for x in y.actions)


def test_tco_policy_stays_within_budget_and_beats_the_age_rule():
    tco, age = run(FLEET, A, "TCO-optimized"), run(FLEET, A, "5-year age")
    assert tco.over_budget == []
    assert tco.pv_cost < age.pv_cost
    assert sum(y.spent for y in tco.years) < sum(y.spent for y in age.years)


def test_platform_roadmap_is_respected():
    with pytest.raises(ValueError):
        from refresh_planner import platform_for
        platform_for(-1, A)
    res = run(FLEET, A, "TCO-optimized")
    assert all(x.platform == "gen6" for y in res.years[:2] for x in y.actions)
    assert all(x.platform == "gen7" for y in res.years[2:] for x in y.actions)
