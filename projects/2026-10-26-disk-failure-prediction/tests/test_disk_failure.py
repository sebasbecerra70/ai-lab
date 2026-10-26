import math
from pathlib import Path

import pytest

from disk_failure import (FEATURES, Costs, LogisticRegression, Scaler, at_threshold, average_precision, best_threshold, features,
                          load, roc_auc, rule_baseline, sigmoid, stratified_split)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def trained():
    rows = load(DATA / "fleet_history.csv")
    train, test = stratified_split(rows)
    scaler = Scaler.fit([features(r) for r in train])
    X = lambda rs: [scaler.transform(features(r)) for r in rs]  # noqa: E731
    model = LogisticRegression(pos_weight=10, epochs=200).fit(X(train), [int(r["failed_30d"]) for r in train])
    return model, model.predict_proba(X(test)), [int(r["failed_30d"]) for r in test], test


def test_sigmoid_is_stable_at_extremes():
    assert sigmoid(0) == 0.5
    assert sigmoid(-1000) == 0.0 and sigmoid(1000) == 1.0


def test_features_log_transform_counts_and_one_hot_models():
    row = {"reallocated_sectors": "0", "pending_sectors": "9", "uncorrectable_errors": "0", "crc_errors": "0",
           "power_on_hours": "20000", "temperature_c": "40", "seek_error_rate": "0.3", "model": "SG-16T"}
    x = features(row)
    assert x["pending_sectors"] == pytest.approx(math.log(10))
    assert x["power_on_hours"] == 2.0
    assert (x["model=SG-16T"], x["model=HX-12T"]) == (1.0, 0.0)
    assert list(x) == FEATURES


def test_stratified_split_keeps_failure_rate():
    rows = load(DATA / "fleet_history.csv")
    train, test = stratified_split(rows)
    rate = lambda rs: sum(r["failed_30d"] == "1" for r in rs) / len(rs)  # noqa: E731
    assert len(train) + len(test) == len(rows)
    assert abs(rate(train) - rate(test)) < 0.002


def test_logistic_regression_learns_a_separable_toy_problem():
    X = [[-2.0], [-1.0], [1.0], [2.0]]
    model = LogisticRegression(l2=0.0, epochs=500).fit(X, [0, 0, 1, 1])
    p = model.predict_proba(X)
    assert p[0] < 0.2 and p[-1] > 0.8 and model.w[0] > 0


def test_auc_and_average_precision_on_known_rankings():
    assert roc_auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert roc_auc([0.5, 0.5], [1, 0]) == 0.5
    assert average_precision([0.9, 0.8, 0.7], [1, 0, 1]) == pytest.approx((1 + 2 / 3) / 2)


def test_threshold_metrics_and_cost():
    r = at_threshold([0.9, 0.6, 0.4, 0.1], [1, 0, 1, 0], 0.5)
    assert (r.tp, r.fp, r.fn, r.tn) == (1, 1, 1, 1)
    assert (r.precision, r.recall) == (0.5, 0.5)
    assert Costs(1000, 100).total(r) == 1 * 1000 + 2 * 100


def test_best_threshold_moves_with_the_cost_ratio():
    scores = [0.95, 0.7, 0.5, 0.3, 0.2, 0.1]
    y = [1, 1, 0, 1, 0, 0]
    cheap_swaps = best_threshold(scores, y, Costs(unplanned_failure=5000, proactive_swap=10))
    pricey_swaps = best_threshold(scores, y, Costs(unplanned_failure=500, proactive_swap=400))
    assert cheap_swaps.recall == 1.0
    assert pricey_swaps.threshold > cheap_swaps.threshold


def test_model_ranks_failures_well_and_learns_the_right_signs(trained):
    model, p, y, _ = trained
    assert roc_auc(p, y) > 0.75
    assert average_precision(p, y) > 5 * sum(y) / len(y)  # far above the 2.5% base rate
    w = dict(zip(FEATURES, model.w))
    assert w["reallocated_sectors"] > 0 and w["pending_sectors"] > 0 and w["power_on_hours"] > 0


def test_model_beats_rule_and_doing_nothing_on_cost(trained):
    _, p, y, test = trained
    costs = Costs()
    model_cost = costs.total(best_threshold(p, y, costs))
    rule_cost = costs.total(at_threshold(rule_baseline(test), y, 0.5))
    nothing = costs.total(at_threshold([0.0] * len(y), y, 0.5))
    assert model_cost < rule_cost and model_cost < nothing
