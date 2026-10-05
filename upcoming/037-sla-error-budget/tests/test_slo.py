from pathlib import Path

import pytest

from slo_budget import (DEFAULT_RULES, AlertRule, BudgetStatus, Incident, Timeline, allowed_downtime_minutes,
                        burn_rate, incident_cost, load_config, load_incidents, match_incidents, replay,
                        sla_credit_pct)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def sample():
    cfg, incidents = load_config(DATA / "slo.json"), load_incidents(DATA / "incidents.csv")
    return cfg, incidents, Timeline.synthesize(cfg, incidents)


def flat(minutes, rpm=100.0, bad_rate=0.0, spikes=()):
    total = [rpm] * minutes
    bad = [rpm * bad_rate] * minutes
    for start, end, rate in spikes:
        for m in range(start, end):
            bad[m] = rpm * rate
    return Timeline(total, bad)


def test_allowed_downtime_for_three_nines():
    assert allowed_downtime_minutes(0.999, 30) == pytest.approx(43.2)
    assert allowed_downtime_minutes(0.9999, 365) == pytest.approx(52.56)


def test_burn_rate_definition():
    assert burn_rate(1, 1000, 0.999) == pytest.approx(1.0)
    assert burn_rate(144, 10000, 0.999) == pytest.approx(14.4)
    assert burn_rate(5, 0, 0.999) == 0.0


def test_budget_status_consumed_and_remaining():
    s = BudgetStatus(0.999, good=999_500, total=1_000_000)
    assert s.consumed == pytest.approx(0.5) and s.remaining == pytest.approx(0.5)
    assert s.sli == pytest.approx(0.9995)


def test_sla_credit_takes_highest_breached_tier():
    tiers = [{"below": 0.999, "credit_pct": 10}, {"below": 0.995, "credit_pct": 25}]
    assert sla_credit_pct(0.9995, tiers) == 0
    assert sla_credit_pct(0.998, tiers) == 10
    assert sla_credit_pct(0.99, tiers) == 25


def test_window_sums_use_prefix_arrays():
    tl = flat(100, rpm=10, bad_rate=0.1)
    assert tl.window(50, 10) == pytest.approx((10.0, 100.0))
    assert tl.window(5, 60) == pytest.approx((5.0, 50.0))  # clipped at start


def test_fast_burn_requires_both_windows():
    # a total outage for 10 minutes: 1h window burn = 1000 * 10/60 > 14.4, 5m window too
    tl = flat(600, spikes=[(200, 210, 1.0)])
    events = replay(tl, 0.999, rules=[DEFAULT_RULES[0]])
    assert len(events) == 1
    ev = events[0]
    assert 200 < ev.fired_at <= 202
    # resolves soon after the short window clears, not after the 1h window drains
    assert ev.resolved_at <= 216


def test_low_level_errors_do_not_page():
    tl = flat(3000, bad_rate=0.002)  # burn rate 2: worth a ticket over days, never a page
    rules = [r for r in DEFAULT_RULES if r.severity == "page"]
    assert replay(tl, 0.999, rules=rules) == []


def test_budget_spent_at_fire_matches_workbook():
    assert DEFAULT_RULES[0].budget_spent_at_fire == pytest.approx(0.02)
    assert DEFAULT_RULES[1].budget_spent_at_fire == pytest.approx(0.05)
    assert DEFAULT_RULES[2].budget_spent_at_fire == pytest.approx(0.10)


def test_sample_month_budget_and_detection(sample):
    cfg, incidents, tl = sample
    bad, total = tl.window(len(tl), len(tl))
    status = BudgetStatus(cfg["slo_target"], total - bad, total)
    assert 0.5 < status.consumed < 0.8
    dets = {d.incident.incident_id: d for d in match_incidents(incidents, replay(tl, cfg["slo_target"], step=1))}
    assert dets["INC-103"].delay_min <= 3
    assert dets["INC-102"].first_alert is None  # slow leak just under the medium-burn threshold


def test_incident_cost_excludes_baseline(sample):
    cfg, incidents, tl = sample
    inc = Incident("x", 1000, 10, 1.0, "")
    tl2 = Timeline.synthesize({**cfg, "baseline_error_rate": 0.0}, [inc])
    assert incident_cost(tl2, inc, 0.0) == pytest.approx(sum(tl2.total[1000:1010]))
