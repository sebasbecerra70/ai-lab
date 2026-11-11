from pathlib import Path

import pytest

from kpi_anomaly import (KpiTable, decompose, detect, detect_naive, load_kpis, naive_z, robust_z, rolling_median,
                         score)

DATA = Path(__file__).resolve().parent.parent / "data"
WEEK = [1.0, 1.0, 1.0, 1.0, 1.0, 0.7, 0.7]


def weekly(n=56, level=1000.0, growth=0.0):
    return [level * (1 + growth * i) * WEEK[i % 7] for i in range(n)]


@pytest.fixture(scope="module")
def table():
    return load_kpis(DATA / "kpis.csv")


def test_rolling_median_ignores_single_spike():
    assert rolling_median([1, 1, 100, 1, 1], 3) == [1, 1, 1, 1, 1]


def test_decompose_recovers_weekly_pattern():
    dec = decompose(weekly())
    assert dec.seasonal[5] / dec.seasonal[0] == pytest.approx(0.7, rel=0.02)
    assert max(abs(r) for r in dec.residual[7:-7]) < 0.01


def test_decompose_handles_trend():
    dec = decompose(weekly(growth=0.01))
    assert dec.trend[40] > dec.trend[10]
    assert max(abs(r) for r in dec.residual[7:-7]) < 0.02


def test_decompose_needs_two_periods():
    with pytest.raises(ValueError):
        decompose([1.0] * 10)


def test_robust_z_is_not_masked_by_the_outlier():
    xs = [0.0, 0.01, -0.01, 0.02, -0.02, 0.0, 5.0]
    assert robust_z(xs)[-1] > 50
    assert naive_z(xs)[-1] < 3  # the outlier inflates the std and hides itself
    assert robust_z([1, 1, 1]) == [0.0, 0.0, 0.0]
    assert robust_z([0, 0, 0, 0, 1])[-1] > 3  # MAD = 0 fallback


def test_injected_spike_on_seasonal_series_is_detected():
    vals = weekly()
    vals[30] *= 0.75  # a weekday drop that looks like a normal weekend level
    t = KpiTable(list(range(1, 57)), ["x"] * 56, {m: list(vals) for m in ["dau", "signups", "conversion_rate", "revenue"]}, set())
    flagged = {(a.day, a.metric) for a in detect(t)}
    assert (31, "dau") in flagged
    assert (31, "dau") not in set(detect_naive(t))


def test_labels_include_downstream_metrics(table):
    assert (24, "dau") in table.labels and (24, "revenue") in table.labels
    assert (97, "revenue") not in table.labels


def test_sample_detection_beats_naive_baseline(table):
    ours = score({(a.day, a.metric) for a in detect(table)}, table.labels)
    naive = score(set(detect_naive(table)), table.labels)
    assert ours.recall >= 0.9 and ours.precision >= 0.7
    assert ours.recall > naive.recall + 0.5


def test_downstream_revenue_moves_are_explained(table):
    by_key = {(a.day, a.metric): a for a in detect(table)}
    assert by_key[(59, "revenue")].explained_by == ["conversion_rate"]
    assert by_key[(78, "revenue")].explained_by == []  # payments issue is its own root cause
    assert by_key[(59, "conversion_rate")].pct_off < -0.25


def test_score_counts():
    s = score({(1, "a"), (2, "a")}, {(1, "a"), (3, "a")})
    assert (s.tp, s.fp, s.fn) == (1, 1, 1)
    assert s.precision == 0.5 and s.recall == 0.5
