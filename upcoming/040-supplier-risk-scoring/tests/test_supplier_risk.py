from dataclasses import replace
from pathlib import Path

import pytest

from supplier_risk import (Country, Scenario, apply, concentration, delivery_score, disruption_probability,
                           financial_score, geo_score, load_countries, load_scenarios, load_suppliers, ramp, run,
                           score, score_all)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    return load_suppliers(DATA / "suppliers.csv"), load_countries(DATA / "countries.csv")


def by_name(suppliers, name):
    return next(s for s in suppliers if s.name == name)


def test_ramp_is_clamped_and_bidirectional():
    assert ramp(2.5, 2.0, 0.8) == 0 and ramp(0.5, 2.0, 0.8) == 100
    assert ramp(1.4, 2.0, 0.8) == pytest.approx(50)
    assert ramp(20, 0, 40) == pytest.approx(50)


def test_financial_score_reacts_to_distress(data):
    s = by_name(data[0], "Lyon Precision Optics")
    assert financial_score(s) == 0
    distressed = replace(s, current_ratio=0.7, debt_to_equity=3.0, net_margin_pct=-6, days_payable_trend=40)
    assert financial_score(distressed) == pytest.approx(100)


def test_geo_and_delivery_scores(data):
    _, countries = data
    assert geo_score(countries["TW"]) > geo_score(countries["DE"])
    s = by_name(data[0], "Ontario Packaging Inc")
    assert delivery_score(s) < delivery_score(by_name(data[0], "Hanoi Plastics Co"))


def test_disruption_probability_calibration():
    assert disruption_probability(25) == pytest.approx(0.03, abs=0.003)
    assert disruption_probability(60) == pytest.approx(0.25, abs=0.01)
    assert disruption_probability(10) < disruption_probability(90)


def test_single_source_doubles_exposure(data):
    suppliers, countries = data
    s = by_name(suppliers, "Bavaria Sensorik GmbH")
    assert score(s, countries).exposure_usd == pytest.approx(2 * score(replace(s, single_source=False), countries).exposure_usd)


def test_ranking_and_tiers(data):
    results = score_all(*data)
    assert results[0].supplier.name == "Shenzhen Precision Electronics"
    tiers = {r.supplier.name: r.tier for r in results}
    assert tiers["Hanoi Plastics Co"] == "critical" and tiers["Ohio Cable & Harness"] == "low"
    assert [r.exposure_usd for r in results] == sorted((r.exposure_usd for r in results), reverse=True)


def test_concentration_shares_sum_to_one(data):
    conc = concentration(data[0])
    hhi = conc.pop("HHI")
    assert sum(conc.values()) == pytest.approx(1.0)
    assert 1 / len(conc) <= hhi <= 1


def test_country_shock_is_capped_and_does_not_mutate_input(data):
    suppliers, countries = data
    sc = Scenario("x", "", {"TW": {"political_risk": 90}}, {}, {})
    _, new_countries = apply(sc, suppliers, countries)
    assert new_countries["TW"].political_risk == 100
    assert countries["TW"].political_risk == 60


def test_lead_time_multiplier_hits_only_listed_countries(data):
    suppliers, countries = data
    new_sup, _ = apply(Scenario("x", "", {}, {"KR": 1.5}, {}), suppliers, countries)
    busan, ohio = by_name(new_sup, "Busan Battery Cells"), by_name(new_sup, "Ohio Cable & Harness")
    assert busan.lead_time_days == pytest.approx(45 * 1.5) and busan.on_time_pct == pytest.approx(92 - 12.5)
    assert ohio == by_name(suppliers, "Ohio Cable & Harness")


def test_sample_scenarios_increase_exposure(data):
    impacts = {sc.name: run(sc, *data) for sc in load_scenarios(DATA / "scenarios.json")}
    blockade = impacts["Taiwan Strait blockade"]
    assert blockade.total_exposure_after > blockade.total_exposure_before * 1.5
    assert ("Taichung Semicon Supply", "medium", "high") in blockade.tier_changes
    assert impacts["Supplier distress"].top_movers[0][0] == "Hanoi Plastics Co"
