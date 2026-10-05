from pathlib import Path

import pytest

from kpi_narrator import (Kpi, MockLLM, Segment, bridge, build_facts, check, fmt, load_kpis, load_segments, narrate,
                          numbers_in, template, variance)

DATA = Path(__file__).resolve().parent.parent / "data"


def kpi(actual, plan, direction="up", tol=5.0, unit="pct", prior=None):
    return Kpi("M", unit, direction, actual, plan, plan if prior is None else prior, tol, "Owner")


def sample_facts():
    vs = [variance(k) for k in load_kpis(DATA / "kpis.csv")]
    return build_facts(vs, bridge(load_segments(DATA / "revenue_drivers.csv")))


class Recorder:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def complete(self, system, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def test_favorability_follows_direction_and_rag_follows_tolerance():
    assert variance(kpi(28.0, 30.0, "down")).favorable
    assert not variance(kpi(31.5, 28.0, "down", tol=5)).favorable
    assert [variance(kpi(a, 100.0, tol=5)).status for a in (110, 96, 92, 89)] == ["green", "green", "amber", "red"]
    # zero tolerance: any miss is red, a beat is green
    assert variance(kpi(1, 0, "down", tol=0, unit="count")).status == "red"
    assert variance(kpi(1, 2, "down", tol=0, unit="count")).status == "green"


def test_formatting_is_consistent():
    assert fmt(4232442, "usd") == "$4.23M" and fmt(-216058, "usd", True) == "-$216k"
    assert fmt(7.42, "usd") == "$7.42" and fmt(0.9, "pct", True) == "+0.9 pp" and fmt(93.1, "pct") == "93.1%"
    assert fmt(61240, "count") == "61,240" and fmt(3.5, "hours", True) == "+3.5 h"


def test_bridge_reconciles_exactly():
    br = bridge(load_segments(DATA / "revenue_drivers.csv"))
    assert br.plan + br.volume + br.mix + br.price == pytest.approx(br.actual)
    for name, e in br.by_segment.items():
        assert set(e) == {"volume", "mix", "price"}


def test_bridge_isolates_each_effect():
    same_mix = bridge([Segment("a", 100, 10, 120, 10), Segment("b", 50, 20, 60, 20)])
    assert same_mix.mix == pytest.approx(0) and same_mix.price == 0 and same_mix.volume == pytest.approx(400)
    shift = bridge([Segment("a", 100, 10, 50, 10), Segment("b", 100, 30, 150, 30)])
    assert shift.volume == 0 and shift.mix == pytest.approx(1000) and shift.price == 0
    price = bridge([Segment("a", 100, 10, 100, 12)])
    assert (price.volume, price.mix, price.price) == (0, 0, 200)


def test_kpi_table_revenue_matches_the_drivers():
    rev = next(k for k in load_kpis(DATA / "kpis.csv") if k.metric == "Revenue")
    orders = next(k for k in load_kpis(DATA / "kpis.csv") if k.metric == "Orders shipped")
    segs = load_segments(DATA / "revenue_drivers.csv")
    br = bridge(segs)
    assert (rev.actual, rev.plan) == (pytest.approx(br.actual), pytest.approx(br.plan))
    assert orders.actual == sum(s.actual_units for s in segs)


def test_number_parser_knows_scale_and_precision():
    got = numbers_in("Revenue $4.23M, gap -$216k, OTD 93.1%, 61,240 orders")
    assert got[0] == ("$4.23M", pytest.approx(4.23e6), pytest.approx(5000))
    assert got[1][1] == 216000 and got[1][2] == 500
    assert got[2][1:] == (93.1, pytest.approx(0.05)) and got[3][1] == 61240


def test_check_accepts_correct_roundings_and_rejects_wrong_ones():
    facts = sample_facts()
    assert check(template(facts), facts) == []
    ok = "Revenue was $4.2M against $4.45M. " + " ".join(k["metric"] for k in facts["kpis"])
    assert check(ok, facts) == []
    assert "number not in facts: $4.3M" in check(ok.replace("$4.2M", "$4.3M"), facts)


def test_check_catches_direction_and_verdict_errors():
    facts = sample_facts()
    names = " ".join(k["metric"] for k in facts["kpis"])
    assert check(f"Order cycle time is above plan; Safety incidents beat plan. {names}", facts) == []
    issues = check(f"Order cycle time beat plan, while Revenue was above plan. {names}", facts)
    assert any("wrong verdict for Order cycle time" in i for i in issues)
    assert any("wrong direction for Revenue" in i for i in issues)


def test_check_requires_every_red_kpi():
    facts = sample_facts()
    issues = check("Revenue missed plan. On-time delivery missed plan.", facts)
    assert "red KPI not mentioned: Employee turnover" in issues
    assert not any("Revenue" in i for i in issues)


def test_repair_loop_fixes_a_sloppy_draft():
    facts = sample_facts()
    n = narrate(MockLLM(sloppy=True), facts)
    assert n.source == "llm" and n.attempts == 2
    assert "number not in facts: $0.25M" in n.issues_by_attempt[0] and n.issues_by_attempt[1] == []
    assert "$216k below plan" in n.text


def test_repeatedly_bad_model_falls_back_to_template_and_sees_its_problems():
    facts = sample_facts()
    rec = Recorder(["Revenue grew 19% and everything beat plan."])
    n = narrate(rec, facts, max_attempts=2)
    assert n.source == "template" and n.text == template(facts)
    assert "number not in facts: 19%" in rec.prompts[1] and "YOUR DRAFT" in rec.prompts[1]


def test_facts_lead_with_the_worst_miss():
    facts = sample_facts()
    assert facts["kpis"][0]["metric"] == "Backorder rate"
    assert (facts["green"], facts["amber"], facts["red"]) == (4, 2, 5)
    assert facts["kpis"][-1]["status"] == "green"
