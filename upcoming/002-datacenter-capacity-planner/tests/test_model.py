from pathlib import Path

import pytest

from capacity_planner import (Hall, Scenario, Site, StepLoad, forecast, headroom, load_halls, load_scenarios,
                              load_site, months_to_exhaust, project, pue)

DATA = Path(__file__).resolve().parent.parent / "data"
SITE = Site(facility_overhead_kw=100, chiller_cop=4.0, utility_feed_kw=10_000, safety_margin=0.9)


def hall(**kw):
    base = dict(name="X", power_capacity_kw=1000, it_load_kw=500, cooling_capacity_kw=1000, cooling_load_kw=550,
                rack_positions=100, racks_installed=40, kw_per_rack_design=10)
    base.update(kw)
    return Hall(**base)


def test_headroom_uses_margin_and_finds_binding_constraint():
    hr = headroom(hall(racks_installed=85), 0.9)
    assert hr.power_kw == pytest.approx(400)
    assert hr.cooling_kw == pytest.approx(350)
    assert hr.racks == pytest.approx(5)
    assert hr.binding == "space"


def test_pue_includes_cooling_electrical_and_overhead():
    # IT 500, cooling 550/4 = 137.5, overhead 100 -> 737.5 / 500
    assert pue([hall()], SITE) == pytest.approx(1.475)
    with pytest.raises(ValueError):
        pue([hall(it_load_kw=0)], SITE)


def test_closed_form_matches_simulation():
    h = hall(cooling_capacity_kw=5000, rack_positions=10_000)
    g = 0.03
    expected = months_to_exhaust(500, 900, g)
    f = forecast([h], SITE, Scenario("s", g), horizon=60)
    assert f.exhaustion["X"]["power"] == expected == 20


def test_already_over_capacity_is_month_zero():
    assert months_to_exhaust(950, 900, 0.02) == 0
    f = forecast([hall(it_load_kw=950)], SITE, Scenario("flat", 0.0), horizon=12)
    assert f.exhaustion["X"]["power"] == 0


def test_no_growth_never_exhausts():
    assert months_to_exhaust(100, 900, 0.0) is None
    f = forecast([hall()], SITE, Scenario("flat", 0.0), horizon=24)
    assert f.first_wall() is None


def test_step_load_lands_in_the_right_hall_and_month():
    s = Scenario("gpu", 0.0, (StepLoad(month=3, hall="X", kw=300, racks=10),))
    before, after = project([hall()], s, 2)[0], project([hall()], s, 3)[0]
    assert before.it_load_kw == 500 and after.it_load_kw == 800
    assert after.cooling_load_kw == pytest.approx(800 * 1.1)  # cooling scales with the hall's ratio
    assert after.racks_installed == 50


def test_step_load_pulls_the_wall_forward():
    base = forecast([hall()], SITE, Scenario("base", 0.02), horizon=60)
    gpu = forecast([hall()], SITE, Scenario("gpu", 0.02, (StepLoad(6, "X", 300, 12),)), horizon=60)
    assert gpu.first_wall()[2] < base.first_wall()[2]
    assert gpu.first_wall()[2] == 6


def test_utility_feed_constraint_tracked_at_site_level():
    small_feed = Site(100, 4.0, utility_feed_kw=800, safety_margin=0.9)
    f = forecast([hall()], small_feed, Scenario("s", 0.01), horizon=60)
    assert f.utility_month == 0  # 737.5 > 720


def test_sample_data_loads_and_ai_cluster_scenario_hits_hall_d():
    halls = load_halls(DATA / "halls.csv")
    site = load_site(DATA / "site.json")
    scenarios = {s.name: s for s in load_scenarios(DATA / "scenarios.json")}
    assert [h.name for h in halls] == ["A", "B", "C", "D"]
    assert 1.2 < pue(halls, site) < 1.6
    ai = forecast(halls, site, scenarios["ai_cluster"], 36)
    base = forecast(halls, site, scenarios["base"], 36)
    assert ai.exhaustion["D"]["power"] is not None
    assert base.exhaustion["D"]["power"] is None or ai.exhaustion["D"]["power"] < base.exhaustion["D"]["power"]


def test_invalid_hall_rejected(tmp_path):
    p = tmp_path / "h.csv"
    p.write_text("hall,power_capacity_kw,it_load_kw,cooling_capacity_kw,cooling_load_kw,rack_positions,"
                 "racks_installed,kw_per_rack_design\nZ,0,10,10,10,10,1,5\n")
    with pytest.raises(ValueError):
        load_halls(p)
