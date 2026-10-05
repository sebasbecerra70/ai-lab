import math
from pathlib import Path

import pytest

from lead_scoring import (LeadScorer, LogisticRegression, Standardizer, auc, lift_at, load_leads, raw_features,
                          sigmoid, train_test_split)

DATA = Path(__file__).resolve().parent.parent / "data" / "leads.csv"


@pytest.fixture(scope="module")
def rows():
    return load_leads(DATA)


@pytest.fixture(scope="module")
def scorer(rows):
    return LeadScorer().fit(train_test_split(rows)[0])


def test_sigmoid_is_stable_at_extremes():
    assert sigmoid(0) == 0.5
    assert sigmoid(-1000) == pytest.approx(0.0) and sigmoid(1000) == pytest.approx(1.0)


def test_logistic_regression_learns_a_simple_boundary_and_loss_falls():
    X = [[x / 10] for x in range(-20, 21)]
    y = [1 if x[0] > 0 else 0 for x in X]
    m = LogisticRegression(lr=0.5, epochs=300, l2=0.0).fit(X, y)
    assert m.weights[0] > 2
    assert m.predict_proba([1.5]) > 0.9 and m.predict_proba([-1.5]) < 0.1
    assert m.loss_history[-1] < m.loss_history[0]


def test_auc_known_values():
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auc([0, 1], [0.5, 0.5]) == 0.5
    assert auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0
    with pytest.raises(ValueError):
        auc([1, 1], [0.2, 0.3])


def test_lift_at_top_fraction():
    y = [1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    scores = [0.9, 0.8] + [0.1] * 8
    assert lift_at(y, scores, 0.2) == pytest.approx(5.0)


def test_raw_features_one_hot_with_baseline_dropped():
    row = {"employees": "1000", "web_visits_30d": "3", "pricing_page_views": "1", "email_opens_30d": "2",
           "demo_requested": "0", "days_since_last_touch": "5", "industry": "logistics", "source": "event"}
    f = raw_features(row)
    assert f["log_employees"] == pytest.approx(3.0)
    assert f["industry=logistics"] == 1.0 and "industry=retail" not in f
    assert not any(k.startswith("source=") and v for k, v in f.items())
    with pytest.raises(ValueError):
        raw_features({**row, "industry": "crypto"})


def test_standardizer_zero_mean_unit_variance_and_constant_column():
    s = Standardizer().fit([{"a": 1.0, "c": 7.0}, {"a": 3.0, "c": 7.0}])
    assert s.transform({"a": 1.0, "c": 7.0}) == [-1.0, 0.0]


def test_model_recovers_ground_truth_directions(scorer):
    coef = dict(scorer.coefficients())
    assert coef["demo_requested"] > 0
    assert coef["pricing_page_views"] > 0
    assert coef["days_since_last_touch"] < 0
    assert coef["industry=logistics"] > coef["industry=education"]


def test_holdout_auc_and_lift_beat_random(rows, scorer):
    test = train_test_split(rows)[1]
    y = [int(r["converted"]) for r in test]
    scores = [scorer.score(r).probability for r in test]
    assert auc(y, scores) > 0.65
    assert lift_at(y, scores, 0.2) > 1.5


def test_explanations_add_up_to_the_logit(rows, scorer):
    lead = scorer.score(rows[0], top_n=100)
    logit = math.log(lead.probability / (1 - lead.probability))
    assert sum(c for _, c in lead.reasons) + scorer.model.bias == pytest.approx(logit)
    assert lead.tier in {"A", "B", "C"}


def test_split_is_deterministic_and_disjoint(rows):
    a, b = train_test_split(rows)
    assert {r["lead_id"] for r in a}.isdisjoint({r["lead_id"] for r in b})
    assert [r["lead_id"] for r in train_test_split(rows)[1]] == [r["lead_id"] for r in b]
