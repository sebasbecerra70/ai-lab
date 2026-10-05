from pathlib import Path

import pytest

from pipeline_forecast import (Deal, DealForecast, at_risk_commits, fit_stage_stats, forecast, load_history, load_pipeline,
                               monte_carlo, p_close_within, percentile, score_deal)
from pipeline_forecast.model import StageStats

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def stats():
    return fit_stage_stats(load_history(DATA / "history.csv"))


def deal(stage="Proposal", amount=100_000, days=5, cat="best_case", id="X"):
    return Deal(id, "Acme", "sam", stage, amount, days, cat)


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([10], 0.9) == 10


def test_win_rate_rises_through_the_funnel(stats):
    rates = [stats[s].win_rate for s in ["Discovery", "Qualified", "Proposal", "Negotiation", "Commit"]]
    assert rates == sorted(rates)
    assert rates[-1] > 0.7 and rates[0] < 0.15


def test_stale_deals_win_less_at_every_stage(stats):
    for s in stats.values():
        assert s.win_rate_stale < s.win_rate_fresh
        assert 0 < s.aging_factor < 1


def test_smoothing_keeps_empty_groups_away_from_zero_and_one():
    st = fit_stage_stats([{"stage": "Commit", "days_in_stage": 3, "won": 1, "days_to_close": 3}])["Commit"]
    assert 0 < st.win_rate_stale < 1
    assert st.win_rate == pytest.approx(2 / 3)


def test_aging_lowers_the_score_of_the_same_deal(stats):
    fresh = score_deal(deal(days=3), stats, 45)
    stale = score_deal(deal(days=200), stats, 45)
    assert stale.stale and not fresh.stale
    assert stale.p_win < fresh.p_win


def test_close_timing_is_conditional_on_time_already_spent():
    st = StageStats("Commit", 0.8, 0.9, 0.5, 10, tuple(range(1, 101)))  # won deals closed 1..100 days after entry
    assert p_close_within(st, elapsed=0, days_left=50) == pytest.approx(0.5)
    assert p_close_within(st, elapsed=50, days_left=50) == pytest.approx(1.0)
    assert p_close_within(st, elapsed=99, days_left=10) == 0.5  # too few comparable deals: neutral prior


def test_more_days_left_never_lowers_the_forecast(stats):
    pipe = load_pipeline(DATA / "pipeline.csv")
    short = forecast(pipe, stats, 15, 900_000, sims=500).weighted
    long = forecast(pipe, stats, 90, 900_000, sims=500).weighted
    assert long > short


def test_monte_carlo_is_reproducible_and_bounded():
    deals = [DealForecast(deal(amount=100_000, id=str(i)), 0.5, 1.0, False) for i in range(10)]
    a, p_a = monte_carlo(deals, 500_000, sims=2_000, seed=1)
    b, p_b = monte_carlo(deals, 500_000, sims=2_000, seed=1)
    assert a == b and p_a == p_b
    assert all(0 <= t <= 1_000_000 for t in a)
    assert sum(a) / len(a) == pytest.approx(500_000 * 0.95, rel=0.03)  # mean haircut of triangular(.85, 1, 1)


def test_sample_forecast_is_ordered_sensibly(stats):
    fc = forecast(load_pipeline(DATA / "pipeline.csv"), stats, 45, 900_000, sims=3_000)
    assert fc.p10 < fc.p50 < fc.p90
    assert fc.weighted < fc.naive_weighted  # aging and timing only ever remove value here
    assert 0 < fc.p_hit_target < 0.5


def test_at_risk_commits_only_flags_commit_deals(stats):
    fc = forecast(load_pipeline(DATA / "pipeline.csv"), stats, 45, 900_000, sims=500)
    risky = at_risk_commits(fc)
    assert risky and all(f.deal.rep_category == "commit" for f in risky)
    assert risky[0].deal.deal_id == "D052"
