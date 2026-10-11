from pathlib import Path

import pytest

from alert_triage import (Alert, TemplateLLM, Topology, correlate, dedupe, draft_summary, incident_facts,
                          load_alerts, parse_time, score, triage)

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def topo():
    return Topology.load(DATA / "topology.json")


@pytest.fixture(scope="module")
def incidents(topo):
    return triage(load_alerts(DATA / "alerts.json"), topo)


def alert(t, host, check="host_down", sev="critical"):
    return Alert(parse_time(t), "test", host, check, sev, "msg")


def test_dedupe_merges_repeats_and_splits_after_gap():
    alerts = [alert("01:00:00", "db-07", "disk_usage"), alert("01:15:00", "db-07", "disk_usage"),
              alert("03:00:00", "db-07", "disk_usage"), alert("01:05:00", "web-01")]
    groups = dedupe(sorted(alerts, key=lambda a: a.seconds), gap_seconds=1800)
    assert [(g.host, len(g.alerts)) for g in groups] == [("db-07", 2), ("web-01", 1), ("db-07", 1)]


def test_upstream_for_hosts_and_infra(topo):
    assert topo.upstream("web-01") == {"PDU-B2", "tor-r12", "CRAC-3"}
    assert topo.upstream("PDU-B2") == {"PDU-B2"}


def test_hosts_sharing_an_alerting_pdu_are_correlated(topo):
    groups = dedupe([alert("02:00:00", "PDU-B2", "pdu_input"), alert("02:00:10", "web-01", "psu_redundancy"),
                     alert("02:00:12", "app-05", "psu_redundancy")])
    incidents = correlate(groups, topo)
    assert len(incidents) == 1 and incidents[0].root_cause == "PDU-B2"


def test_shared_but_healthy_component_does_not_merge(topo):
    # web-01 and db-07 share CRAC-3, but CRAC-3 is not alerting, so these are separate problems.
    groups = dedupe([alert("02:00:00", "web-01"), alert("02:00:30", "db-07", "disk_usage", "warning")])
    assert len(correlate(groups, topo)) == 2


def test_time_window_separates_incidents(topo):
    groups = dedupe([alert("02:00:00", "tor-r14", "interface_flap", "major"),
                     alert("03:00:00", "cache-02", "latency_high", "warning")])
    assert len(correlate(groups, topo, window_seconds=300)) == 2


def test_sample_night_collapses_to_five_incidents(incidents):
    assert sum(i.alert_count for i in incidents) == 28
    assert [(i.severity, i.root_cause) for i in incidents] == [
        ("SEV1", "PDU-B2"), ("SEV2", "tor-r14"), ("SEV2", "CRAC-4"), ("SEV3", "db-07"), ("SEV4", "batch-03")]


def test_severity_rises_with_tier1_availability_impact(topo):
    only_psu = correlate(dedupe([alert("02:00:00", "web-01", "psu_redundancy", "warning")]), topo)[0]
    outage = correlate(dedupe([alert("02:00:00", "web-01", "http_5xx"), alert("02:00:05", "web-02", "http_5xx")]),
                       topo)[0]
    assert score(only_psu, topo).severity == "SEV4"
    assert score(outage, topo).points > only_psu.points
    assert outage.severity in {"SEV1", "SEV2"}


def test_facts_are_structured_for_the_llm(incidents):
    facts = incident_facts(incidents)
    assert facts[0]["severity"] == "SEV1" and facts[0]["started"] == "02:14:05"
    assert "checkout (tier 1)" in facts[0]["services"]


def test_summary_prioritizes_and_defers_noise(incidents):
    text = draft_summary(incidents, TemplateLLM())
    lines = text.splitlines()
    assert lines[0].startswith("- SEV1") and "PDU-B2" in lines[0] and "dispatch DC tech" in lines[0]
    assert "Can wait until morning: batch-03" in lines[-1]


def test_llm_receives_facts_and_strict_system_prompt(incidents):
    class Spy:
        def complete(self, system, prompt):
            self.system, self.prompt = system, prompt
            return "ok"

    spy = Spy()
    draft_summary(incidents, spy)
    assert "ONLY the incident facts" in spy.system and '"root_cause_candidate": "PDU-B2"' in spy.prompt
