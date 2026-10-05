import math
from pathlib import Path

import pytest

from safety_stock import Sku, load, portfolio_value, reorder_point, safety_stock_csl, safety_stock_fill, simulate, tradeoff_curve
from safety_stock import normal

DATA = Path(__file__).resolve().parent.parent / "data"


def sku(d=100, sd_d=20, lt=4, sd_lt=1, q=500, cost=10.0, abc="A"):
    return Sku("X", "test", cost, q, abc, d, sd_d, lt, sd_lt)


def test_normal_helpers_match_textbook_values():
    assert normal.cdf(0) == pytest.approx(0.5)
    assert normal.ppf(0.95) == pytest.approx(1.6449, abs=1e-4)
    assert normal.ppf(0.98) == pytest.approx(2.0537, abs=1e-4)
    assert normal.loss(0) == pytest.approx(0.3989, abs=1e-4)
    assert normal.loss(normal.z_for_loss(0.05)) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        normal.ppf(1.0)


def test_sigma_ltd_combines_both_variances():
    s = sku()
    assert s.sigma_ltd == pytest.approx(math.sqrt(4 * 20 ** 2 + 100 ** 2 * 1 ** 2))  # sqrt(1600 + 10000)
    assert s.sigma_demand_only == pytest.approx(40)
    assert s.lt_share == pytest.approx(10000 / 11600)


def test_csl_safety_stock_and_reorder_point():
    s = sku()
    ss = safety_stock_csl(s, 0.95)
    assert ss == pytest.approx(1.6449 * math.sqrt(11600), rel=1e-4)
    assert reorder_point(s, ss) == pytest.approx(400 + ss)
    assert safety_stock_csl(s, 0.3) == 0.0  # below 50% the formula would go negative


def test_fill_rate_safety_stock_falls_as_order_quantity_grows():
    small, large = sku(q=200), sku(q=2000)
    assert safety_stock_fill(large, 0.99) < safety_stock_fill(small, 0.99)
    s = sku(q=500)
    ss = safety_stock_fill(s, 0.99)
    expected_short = s.sigma_ltd * normal.loss(ss / s.sigma_ltd)
    assert expected_short == pytest.approx(0.01 * 500, rel=1e-4)


def test_no_lead_time_variance_reduces_to_textbook_formula():
    s = sku(sd_lt=0)
    assert safety_stock_csl(s, 0.95) == pytest.approx(normal.ppf(0.95) * 20 * 2)


def test_tradeoff_curve_is_increasing_and_convex_at_the_top():
    skus = load(DATA)
    curve = tradeoff_curve(skus, [0.90, 0.95, 0.99, 0.999])
    values = [p.value for p in curve]
    assert values == sorted(values)
    # the last 0.9 points of service cost more than the 4 points from 95% to 99%
    assert curve[3].marginal > curve[2].marginal


def test_abc_tiering_is_cheaper_than_flat_service():
    skus = load(DATA)
    flat = portfolio_value(skus, {"A": 0.98, "B": 0.98, "C": 0.98})
    tiered = portfolio_value(skus, {"A": 0.98, "B": 0.95, "C": 0.90})
    assert tiered < flat


def test_loader_estimates_stats_from_history():
    skus = {s.sku: s for s in load(DATA)}
    assert len(skus) == 8
    brg = skus["BRG-710"]
    assert 350 < brg.d < 420 and 2.0 < brg.lt < 3.2
    assert brg.lt_share > 0.75  # supplier variability dominates this SKU's risk


def test_simulation_hits_the_target_service_level():
    s = sku(d=100, sd_d=25, lt=3, sd_lt=0.5, q=300)
    ss = safety_stock_csl(s, 0.95)
    full = simulate(s, reorder_point(s, ss), weeks=3000, seed=3)
    naive = simulate(s, s.d * s.lt + ss / s.sigma_ltd * s.sigma_demand_only, weeks=3000, seed=3)
    assert full.csl == pytest.approx(0.95, abs=0.03)
    assert naive.csl < full.csl - 0.03
    assert full.fill_rate > full.csl  # most stockouts are partial, so fill rate sits above CSL


def test_simulation_is_seeded():
    s = sku()
    assert simulate(s, 600, weeks=200, seed=7) == simulate(s, 600, weeks=200, seed=7)
