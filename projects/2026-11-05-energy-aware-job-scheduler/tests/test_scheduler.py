from pathlib import Path

import pytest

from energy_scheduler import (GridHour, InfeasibleError, Job, evaluate, hour_score, load_grid, load_jobs,
                              schedule_asap, schedule_optimized, tradeoff_curve)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def inputs():
    return load_jobs(DATA / "jobs.csv"), load_grid(DATA / "grid_48h.csv")


def flat_grid(prices, carbon=None):
    carbon = carbon or [400] * len(prices)
    return [GridHour(h, p, c) for h, (p, c) in enumerate(zip(prices, carbon))]


def test_loaders_parse_sample_data(inputs):
    jobs, grid = inputs
    assert len(grid) == 48 and len(jobs) == 12
    assert any(j.preemptible for j in jobs) and any(not j.preemptible for j in jobs)


def test_hour_score_adds_carbon_shadow_price():
    g = GridHour(0, 50.0, 400.0)
    assert hour_score(g, 0) == 50.0
    assert hour_score(g, 100) == pytest.approx(90.0)  # 0.4 t/MWh * $100


def test_non_preemptible_job_takes_cheapest_contiguous_window():
    grid = flat_grid([90, 80, 10, 12, 70, 60])
    job = Job("a", "t", 100, 2, 0, 6, False)
    assert schedule_optimized([job], grid).hours["a"] == [2, 3]


def test_preemptible_job_picks_cheapest_hours_anywhere():
    grid = flat_grid([10, 90, 15, 90, 12, 90])
    job = Job("a", "t", 100, 3, 0, 6, True)
    assert schedule_optimized([job], grid).hours["a"] == [0, 2, 4]


def test_capacity_cap_is_respected_and_pushes_second_job():
    grid = flat_grid([10, 50, 60])
    jobs = [Job("a", "t", 600, 1, 0, 3, False), Job("b", "t", 600, 1, 0, 3, False)]
    s = schedule_optimized(jobs, grid, cap_kw=1000)
    assert sorted([s.hours["a"][0], s.hours["b"][0]]) == [0, 1]
    assert max(s.load_kw(jobs, 3)) <= 1000


def test_infeasible_deadline_raises():
    grid = flat_grid([10, 10])
    with pytest.raises(InfeasibleError):
        schedule_optimized([Job("a", "t", 100, 3, 0, 2, False)], grid)
    with pytest.raises(InfeasibleError):
        schedule_asap([Job("a", "t", 100, 3, 0, 2, False)], grid)


def test_optimized_beats_asap_and_meets_deadlines(inputs):
    jobs, grid = inputs
    base = evaluate(schedule_asap(jobs, grid, 900), jobs, grid)
    opt = evaluate(schedule_optimized(jobs, grid, 900, 0), jobs, grid)
    assert opt.deadlines_met and base.deadlines_met
    assert opt.cost_usd < base.cost_usd * 0.9
    assert opt.peak_kw <= 900


def test_higher_carbon_price_never_increases_emissions_much(inputs):
    jobs, grid = inputs
    curve = tradeoff_curve(jobs, grid, 900, carbon_prices=(0, 500))
    (_, cheap), (_, green) = curve
    assert green.carbon_kg < cheap.carbon_kg
    assert green.cost_usd >= cheap.cost_usd - 1e-6


def test_energy_accounting_matches_job_definitions(inputs):
    jobs, grid = inputs
    s = schedule_optimized(jobs, grid, 900, 100)
    total_mwh = sum(sum(1 for _ in s.hours[j.job_id]) * j.power_kw / 1000 for j in jobs)
    assert total_mwh == pytest.approx(sum(j.energy_mwh for j in jobs))
