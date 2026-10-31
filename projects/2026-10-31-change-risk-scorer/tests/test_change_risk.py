import json
from pathlib import Path

import pytest

from change_risk import (Change, failure_rates, in_peak, in_window, likelihood, load_changes, load_history,
                         load_topology, score_all, simulate, single_points_of_failure)

DATA = Path(__file__).resolve().parent.parent / "data"
TOPO = load_topology(DATA / "topology.json")
CAL = json.loads((DATA / "calendar.json").read_text())


def change(**kw):
    base = dict(id="CHG-1", title="t", type="config", targets=["reporting"], start="2026-11-22T02:00",
                end="2026-11-22T03:00", rollback={"tested": True, "minutes": 10}, peer_reviewed=True,
                tested_in_staging=True)
    base.update(kw)
    return Change.from_dict(base)


def test_dual_corded_rack_survives_one_feed_single_corded_does_not():
    out = simulate(TOPO, {"pdu-A1"})
    assert out.down == {"pdu-A1"}
    assert {"rack-01", "rack-02"} <= out.degraded
    out = simulate(TOPO, {"pdu-A2"})
    assert {"rack-03", "db-replica", "backup-svc", "reporting"} <= out.down
    assert "customer-portal" in out.degraded  # still served by db-primary


def test_failures_cascade_through_the_graph():
    out = simulate(TOPO, {"storage-array"})
    assert out.customer_down(TOPO) == ["billing-api", "customer-portal"]
    with pytest.raises(ValueError, match="unknown"):
        simulate(TOPO, {"ghost"})


def test_spofs_are_only_the_ones_the_change_creates():
    spofs = single_points_of_failure(TOPO, {"ups-B"})
    assert "ups-A" in spofs and "pdu-A1" in spofs
    assert "firewall-ha" not in spofs  # a SPOF already, not caused by this change
    assert single_points_of_failure(TOPO, {"reporting"}) == {}


def test_failure_rates_are_smoothed_toward_the_prior():
    rows = [{"type": "firmware", "outcome": "success"}] * 3 + [{"type": "config", "outcome": "rolled_back"}]
    rates = failure_rates(rows)
    assert rates["firmware"] == pytest.approx(1 / 13)  # 0 of 3 is not 0% risk
    assert rates["config"] == pytest.approx(2 / 11)
    real = failure_rates(load_history(DATA / "history.csv"))
    assert real["config"] < real["firmware"]


def test_missing_evidence_raises_likelihood_and_staging_only_counts_for_software():
    rates = {"firmware": 0.10, "hardware-swap": 0.10}
    p_good, _ = likelihood(change(type="firmware"), rates)
    p_bad, band = likelihood(change(type="firmware", tested_in_staging=False, peer_reviewed=False), rates)
    assert p_bad == pytest.approx(p_good * 1.5 * 1.3) and band == 5
    assert likelihood(change(type="hardware-swap", tested_in_staging=False), rates)[0] == pytest.approx(0.10)


def test_window_and_peak_checks():
    assert in_window(change(), CAL)  # Sunday 02:00-03:00 inside 01:00-05:00
    late = change(start="2026-11-22T04:30", end="2026-11-22T05:30")
    assert not in_window(late, CAL)
    assert in_peak(change(start="2026-11-17T14:00", end="2026-11-17T15:00"), CAL)  # Tuesday afternoon
    assert not in_peak(change(start="2026-11-22T14:00", end="2026-11-22T15:00"), CAL)  # weekend
    with pytest.raises(ValueError, match="end must be after start"):
        change(end="2026-11-22T01:00")


def test_two_safe_changes_that_overlap_are_both_blocked():
    a = change(id="A", type="power-maintenance", targets=["ups-B"])
    b = change(id="B", type="hardware-swap", targets=["pdu-A1"])
    res = {x.change.id: x for x in score_all([a, b], TOPO, {}, CAL)}
    assert all(x.recommendation == "REJECT / RESCHEDULE" for x in res.values())
    assert "together they take down billing-api, customer-portal" in res["A"].blockers[0]
    b_later = change(id="B", type="hardware-swap", targets=["pdu-A1"], start="2026-11-22T03:00", end="2026-11-22T04:00")
    assert all(not x.blockers for x in score_all([a, b_later], TOPO, {}, CAL))


def test_freeze_and_irreversible_changes_are_blocked():
    c = change(type="software-deploy", targets=["db-primary"], start="2026-12-30T02:00", end="2026-12-30T03:00",
               rollback={"tested": False, "minutes": None})
    [a] = score_all([c], TOPO, {}, CAL)
    assert any("freeze" in b for b in a.blockers) and any("irreversible" in b for b in a.blockers)
    assert a.impact == 5


def test_routine_config_is_standard_and_sample_agenda_is_ordered():
    [a] = score_all([change()], TOPO, {"config": 0.04}, CAL)
    assert a.recommendation == "STANDARD (pre-approved)"
    agenda = score_all(load_changes(DATA / "changes.json"), TOPO, failure_rates(load_history(DATA / "history.csv")), CAL)
    recs = {x.change.id: x.recommendation for x in agenda}
    assert recs["CHG-1044"].startswith("REJECT") and recs["CHG-1045"].startswith("STANDARD")
    assert [x.blockers != [] for x in agenda] == sorted((x.blockers != [] for x in agenda), reverse=True)
    with pytest.raises(ValueError, match="duplicate"):
        score_all([change(), change()], TOPO, {}, CAL)
