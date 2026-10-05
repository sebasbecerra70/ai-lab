import json
from pathlib import Path

import pytest

from postmortem import (MockLLM, action_items, build_facts, build_timeline, classify, collapse, compute_metrics,
                        draft_postmortem, lint, load_timeline, parse_chat, parse_logs)

DATA = Path(__file__).resolve().parent.parent / "data"
ROLES = json.loads((DATA / "roles.json").read_text())


@pytest.fixture(scope="module")
def events():
    return load_timeline(DATA)


def test_parse_logs_skips_garbage_lines():
    evs = parse_logs("02:00:00 web-1 ERROR disk full\nnot a log line\n02:00:05 web-1 INFO ok")
    assert [(e.time, e.level, e.kind) for e in evs] == [("02:00:00", "ERROR", "fault"), ("02:00:05", "INFO", "info")]


@pytest.mark.parametrize("text, level, kind", [
    ("change CHG-1 applied: x", "INFO", "change"),
    ("change CHG-1 rolled back: x", "INFO", "mitigation"),
    ("page sent: DiskFull to oncall", "INFO", "alert"),
    ("decision: freeze deploys", "CHAT", "decision"),
    ("port down", "WARN", "symptom"),
])
def test_classify_rules(text, level, kind):
    assert classify(text, level) == kind


def test_collapse_merges_same_message_across_hosts_within_window():
    evs = parse_logs("01:00:00 h1 ERROR psu lost\n01:00:01 h2 ERROR psu lost\n01:05:00 h3 ERROR psu lost")
    out = collapse(evs)
    assert [e.sources for e in out] == [["h1", "h2"], ["h3"]]


def test_chat_and_logs_merge_in_time_order(events):
    times = [e.t for e in events]
    assert times == sorted(times)
    assert {e.level for e in events} >= {"CHAT", "ERROR", "INFO"}


def test_metrics_measure_from_first_fault(events):
    m = compute_metrics(events)
    assert m.start == "02:14:05"
    assert m.durations() == {"time_to_detect": "1m57s", "time_to_acknowledge": "2m35s",
                             "time_to_mitigate": "10m25s", "time_to_resolve": "47m55s"}
    assert "CHG-4471" in m.suspected_change


def test_change_outside_lookback_is_not_blamed():
    evs = build_timeline("00:00:00 cfg INFO change CHG-1 applied: x\n02:00:00 db ERROR down", "")
    assert compute_metrics(evs).suspected_change is None


def test_no_faults_means_no_postmortem():
    with pytest.raises(ValueError):
        compute_metrics(parse_chat('{"time": "01:00:00", "user": "a", "text": "all quiet"}'))


def test_action_items_follow_from_evidence(events):
    actions = " ".join(a["action"] for a in action_items(events, compute_metrics(events)))
    assert "Canary PDU firmware" in actions and "single PSU" in actions and "breaker-trip" in actions


def test_facts_use_roles_instead_of_names(events):
    facts = build_facts(events, compute_metrics(events), "t", ROLES)
    blob = json.dumps(facts)
    assert "priya" not in blob and "marcus" not in blob
    assert "on-call SRE" in blob


def test_mock_draft_passes_lint(events):
    facts = build_facts(events, compute_metrics(events), "t", ROLES)
    result = lint(draft_postmortem(MockLLM(), facts), facts)
    assert result.ok, result


def test_lint_catches_blame_invented_times_and_missing_sections(events):
    facts = build_facts(events, compute_metrics(events), "t", ROLES)
    bad = "# Summary\nThe tech should have checked the PSU. Human error at 04:12 caused it."
    r = lint(bad, facts)
    assert [p.lower() for p in r.blame_phrases] == ["human error", "should have"]
    assert r.unknown_times == ["04:12"]
    assert "Action items" in r.missing_sections
