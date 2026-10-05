import math
from pathlib import Path

import pytest

from demand_forecast import (backtest, bias, croston, evaluate, holt_winters, holt_winters_fit, intermittency,
                             load_series, mape, moving_average, naive, seasonal_naive, wape)
from demand_forecast.backtest import wape_totals

DATA = Path(__file__).resolve().parent.parent / "data" / "weekly_demand.csv"


def test_metrics_on_known_values():
    assert wape([10, 10], [12, 8]) == pytest.approx(0.2)
    assert mape([10, 0, 20], [11, 5, 18]) == pytest.approx(0.1)  # zero actual skipped
    assert mape([0, 0], [1, 1]) is None
    assert bias([10, 10], [12, 12]) == pytest.approx(0.2)
    assert wape_totals([1, 0, 0, 1], [0.5, 0.5, 0.5, 0.5], 4) == 0.0


def test_naive_seasonal_naive_and_moving_average():
    assert naive([1, 2, 3], 2) == [3, 3]
    assert seasonal_naive(4)([1, 2, 3, 4, 5, 6, 7, 8], 6) == [5, 6, 7, 8, 5, 6]
    assert moving_average(3)([1, 2, 3, 4, 5], 2) == [4.0, 4.0]


def test_holt_winters_recovers_pure_seasonal_pattern():
    season = 4
    y = [10 + [5, -5, 2, -2][t % season] + 0.5 * t for t in range(24)]
    fc = holt_winters(season)(y, 4)
    expected = [10 + [5, -5, 2, -2][t % season] + 0.5 * t for t in range(24, 28)]
    assert fc == pytest.approx(expected, abs=1.0)


def test_holt_winters_needs_two_seasons():
    with pytest.raises(ValueError):
        holt_winters_fit([1.0] * 7, 4, 0.3, 0.1, 0.3)
    assert holt_winters(4)([1.0, 2.0, 3.0], 2) == [3.0, 3.0]  # falls back to naive


def test_croston_rate_and_sba_correction():
    y = [0, 0, 4, 0, 0, 4, 0, 0, 4]
    plain = croston(alpha=0.1, sba=False)(y, 1)[0]
    assert plain == pytest.approx(4 / 3)
    assert croston(alpha=0.1, sba=True)(y, 1)[0] == pytest.approx(plain * 0.95)
    assert croston()([0, 0, 0], 2) == [0.0, 0.0]


def test_intermittency_adi():
    assert intermittency([1, 1, 1, 1]) == 1.0
    assert intermittency([0, 3, 0, 0, 2, 0, 0, 1]) == 3.0
    assert math.isinf(intermittency([0, 0, 5]))


def test_backtest_uses_only_past_data():
    seen = []

    def spy(history, h):
        seen.append(len(history))
        return [0.0] * h

    actual, pred = backtest(list(range(20)), spy, horizon=4, origins=3)
    assert seen == [8, 12, 16]
    assert actual == list(range(8, 20)) and len(pred) == 12
    with pytest.raises(ValueError):
        backtest([1, 2, 3], spy, horizon=4, origins=3)


@pytest.fixture(scope="module")
def series():
    return load_series(DATA)


def test_sample_winners_match_demand_patterns(series):
    from demand_forecast import default_models
    winners = {sku: evaluate(y, default_models())[0].model for sku, y in series.items()}
    assert winners["SKU-STRETCH-WRAP"] in {"holt_winters", "seasonal_naive"}
    assert winners["SKU-SPARE-MOTOR"] == "croston_sba"
    assert winners["SKU-GLOVES-L"] == "moving_avg_8"


def test_seasonal_models_beat_naive_on_seasonal_sku(series):
    scores = {s.model: s.wape for s in evaluate(series["SKU-STRETCH-WRAP"],
                                                {"naive": naive, "hw": holt_winters(52)})}
    assert scores["hw"] < scores["naive"]
