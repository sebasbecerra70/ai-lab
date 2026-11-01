import math
from dataclasses import replace
from pathlib import Path

import pytest

from churn import (HORIZON, Account, ChurnModel, auc, blended_curve, feature_names, label, load_accounts,
                   months_observed, raw_features, retention_triangle, sigmoid, split)

DATA = Path(__file__).resolve().parent.parent / "data"


def acct(i=0, cohort=1, churn=None, **kw):
    base = dict(account_id=f"A{i}", cohort=cohort, plan="team", seats=10, billing="monthly", onboarding_completed=1,
                active_days_first30=15, integrations_first30=1, support_tickets_first30=1, churn_month=churn)
    base.update(kw)
    return Account(**base)


def test_triangle_only_reports_months_a_cohort_has_lived():
    accounts = [acct(1, 1, None), acct(2, 1, 2), acct(3, 2, 1), acct(4, 2, None), acct(5, 3, None)]
    tri = retention_triangle(accounts)
    assert tri[1] == [1.0, 0.5, 0.5]  # cohort 1 has 3 months of history
    assert tri[2] == [0.5, 0.5]
    assert tri[3] == [1.0]
    assert months_observed(accounts[0], 3) == 3


def test_kaplan_meier_curve_uses_every_cohort_and_never_rises():
    accounts = [acct(1, 1, None), acct(2, 1, 2), acct(3, 2, 1), acct(4, 2, None), acct(5, 3, None)]
    # month 1: 1 of 5 churns; month 2: 1 of the 3 still at risk with 2+ months of history; month 3: 0 of 1
    assert blended_curve(accounts) == pytest.approx([0.8, 0.8 * (2 / 3), 0.8 * (2 / 3)])
    real = blended_curve(load_accounts(DATA / "accounts.csv"))
    assert all(b <= a for a, b in zip(real, real[1:]))


def test_label_and_feature_encoding():
    assert label(acct(churn=HORIZON)) == 1 and label(acct(churn=HORIZON + 1)) == 0 and label(acct()) == 0
    x = dict(zip(feature_names(), raw_features(acct(plan="business", billing="annual"))))
    assert x["plan=business"] == 1 and x["plan=team"] == 0 and x["billing=annual"] == 1
    assert len(x) == len(feature_names())


def test_sigmoid_is_stable_at_extremes():
    assert sigmoid(0) == 0.5
    assert sigmoid(800) == 1.0 and sigmoid(-800) == 0.0


def test_auc_handles_ties_and_matches_pairwise_definition():
    assert auc([1, 0, 1, 0], [0.9, 0.1, 0.4, 0.6]) == pytest.approx(0.75)
    assert auc([1, 0], [0.5, 0.5]) == 0.5
    with pytest.raises(ValueError):
        auc([1, 1], [0.2, 0.3])


def test_model_learns_a_planted_effect_and_starts_at_the_base_rate():
    rows = [acct(i, churn=2 if i % 2 else None, active_days_first30=3 if i % 2 else 25) for i in range(40)]
    m = ChurnModel(epochs=1).fit(rows)
    assert sigmoid(m.bias) == pytest.approx(0.5)
    m = ChurnModel().fit(rows)
    assert m.predict(acct(active_days_first30=2)) > 0.8 > 0.2 > m.predict(acct(active_days_first30=28))
    assert m.drivers()[0][0] == "active_days_first30" and m.drivers()[0][1] < 1
    with pytest.raises(ValueError):
        ChurnModel().fit([acct(churn=None)] * 3)


@pytest.fixture(scope="module")
def trained():
    accounts = load_accounts(DATA / "accounts.csv")
    mature = [a for a in accounts if months_observed(a, 12) >= HORIZON]
    train, test = split(mature)
    return ChurnModel().fit(train), test


def test_model_beats_single_signal_baseline_on_holdout(trained):
    model, test = trained
    y = [label(a) for a in test]
    model_auc = auc(y, [model.predict(a) for a in test])
    assert model_auc > 0.8
    assert model_auc > auc(y, [-a.active_days_first30 for a in test])


def test_drivers_point_the_right_way_and_reasons_explain_risk(trained):
    model, _ = trained
    odds = dict(model.drivers())
    assert odds["billing=annual"] < 1 and odds["active_days_first30"] < 1 and odds["integrations_first30"] < 1
    risky = acct(plan="starter", billing="monthly", active_days_first30=1, integrations_first30=0, onboarding_completed=0)
    assert model.predict(risky) > 0.7
    assert any("active days 1" in r for r in model.reasons(risky))
    assert model.predict(replace(risky, onboarding_completed=1, integrations_first30=2)) < model.predict(risky)
    assert not math.isnan(model.predict(risky))
