from pathlib import Path

import pytest

from delay_risk import (Stump, StumpEnsemble, auc, baseline_rates, brier, dataset, featurize, lane_carrier_matrix,
                        load_rows, precision_at, score_plan, tier, time_split)

DATA = Path(__file__).resolve().parent.parent / "data"


def row(**kw):
    base = dict(shipment_id="S1", week="1", lane="ATL-CHI", carrier="Redline", mode="FTL", distance_km="1150",
                planned_days="2", ship_dow="Tue", peak_season="0", weather_index="0.2", carrier_otp_90d="0.95",
                delayed="0")
    base.update({k: str(v) for k, v in kw.items()})
    return base


def test_featurize_derives_slack_and_cross_border():
    x = featurize(row(lane="LAR-MTY", distance_km=240, planned_days=1))
    assert x["schedule_slack"] == pytest.approx(700 / 240, abs=1e-3)
    assert x["cross_border"] == "yes"
    assert featurize(row())["cross_border"] == "no"


def test_time_split_trains_on_the_past_only():
    rows = [row(shipment_id=f"S{i}", week=w) for i, w in enumerate([5, 1, 3, 2, 4, 0, 7, 6])]
    train, test = time_split(rows, 0.25)
    assert max(int(r["week"]) for r in train) < min(int(r["week"]) for r in test)
    assert len(test) == 2


def test_stump_votes_and_describes_both_kinds_of_split():
    s = Stump("weather_index", "<=", 0.5, -1, 1.0)  # mild weather -> on time
    assert s.vote({"weather_index": 0.2}) == -1 and s.vote({"weather_index": 0.8}) == 1
    assert s.describe({"weather_index": 0.8}) == "weather_index > 0.5"
    c = Stump("ship_dow", "==", "Mon", -1, 1.0)
    assert c.describe({"ship_dow": "Thu"}) == "ship_dow=Thu (not Mon)"


def test_ensemble_learns_a_single_rule_perfectly():
    X = [featurize(row(carrier=c, weather_index=w)) for c in ("Redline", "Crestway", "Bluewater") for w in (0.1, 0.3, 0.5)]
    y = [0, 0, 0, 1, 1, 1, 0, 0, 0]  # only Crestway is late
    m = StumpEnsemble(5).fit(X, y)
    assert m.stumps[0].feature == "carrier"
    assert all((m.predict_proba(x) > 0.5) == bool(t) for x, t in zip(X, y))
    assert m.reasons(X[3]) == ["carrier=Crestway"]


def test_ensemble_rejects_one_class_or_mismatched_data():
    X = [featurize(row())] * 3
    with pytest.raises(ValueError, match="both"):
        StumpEnsemble().fit(X, [0, 0, 0])
    with pytest.raises(ValueError):
        StumpEnsemble().fit(X, [0, 1])


def test_auc_brier_and_precision_on_hand_computed_cases():
    y, p = [1, 1, 0, 0], [0.9, 0.4, 0.5, 0.1]
    assert auc(y, p) == pytest.approx(0.75)  # 3 of 4 delayed/on-time pairs ordered correctly
    assert auc([1, 0], [0.5, 0.5]) == 0.5
    assert brier([1, 0], [1.0, 0.0]) == 0 and brier([1], [0.0]) == 1
    assert precision_at(y, p, 2) == 0.5


def test_tiers_and_baseline_rates():
    assert [tier(p) for p in (0.6, 0.35, 0.1)] == ["HIGH", "watch", "ok"]
    rates = baseline_rates([row(carrier="A", delayed=1), row(carrier="A", delayed=0), row(carrier="B")], "carrier")
    assert rates == {"A": 0.5, "B": 0.0}


@pytest.fixture(scope="module")
def trained():
    rows = load_rows(DATA / "shipments.csv")
    train, test = time_split(rows)
    return rows, train, test, StumpEnsemble(40).fit(*dataset(train))


def test_model_beats_carrier_history_on_holdout(trained):
    _, train, test, model = trained
    Xte, yte = dataset(test)
    rate = baseline_rates(train, "carrier")
    model_auc = auc(yte, [model.predict_proba(x) for x in Xte])
    assert model_auc > 0.65
    assert model_auc > auc(yte, [rate[r["carrier"]] for r in test])


def test_matrix_isolates_carrier_effect_and_plan_suggests_swaps(trained):
    rows, _, _, model = trained
    matrix = lane_carrier_matrix(model, rows)
    for by_carrier in matrix.values():
        assert by_carrier["Crestway"] > by_carrier["Redline"]  # worst vs best carrier in the generator
    plan = load_rows(DATA / "upcoming.csv")
    otp = {"Redline": 0.95, "Bluewater": 0.9, "Crestway": 0.81, "Northpass": 0.87}
    scored = score_plan(model, plan, sorted(otp), otp)
    assert [r.risk for r in scored] == sorted((r.risk for r in scored), reverse=True)
    for r in scored:
        if r.swap:
            assert r.swap[0] != r.carrier and r.risk - r.swap[1] >= 0.10
