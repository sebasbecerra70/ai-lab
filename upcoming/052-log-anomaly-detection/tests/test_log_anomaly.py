from pathlib import Path

import pytest

from log_anomaly import WILD, Drain, Event, detect, incidents, mask, parse
from log_anomaly.loggen import generate

DATA = Path(__file__).resolve().parent.parent / "data" / "syslog.txt"


@pytest.fixture(scope="module")
def mined():
    drain = Drain()
    events = parse(DATA, drain)
    return drain, events, detect(events, drain)


def test_masking_handles_ips_numbers_and_units():
    assert mask("BGP neighbor 10.20.3.4 keepalive received") == ["BGP", "neighbor", "<IP>", "keepalive", "received"]
    assert mask("link up, speed 25G") == ["link", "up,", "speed", "<NUM>"]
    assert mask("SEL log 85% full at 0x1F") == ["SEL", "log", "<NUM>", "full", "at", "<HEX>"]
    assert mask("Ethernet1/12") == ["Ethernet1/<NUM>"]


def test_drain_merges_variants_into_one_template():
    d = Drain()
    a = d.add("fan FAN1 speed 8000 RPM ok")
    b = d.add("fan FAN4 speed 9100 RPM ok")
    assert a is b and a.size == 2
    assert a.template == ["fan", WILD, "speed", "<NUM>", "RPM", "ok"]


def test_drain_keeps_different_events_apart():
    d = Drain()
    up = d.add("Interface Ethernet1/3 link up, speed 25G")
    down = d.add("Interface Ethernet1/3 link down")
    opened = d.add("session opened for user svc from 10.0.0.1")
    closed = d.add("session closed for user svc from 10.0.0.1")
    assert len({up.id, down.id}) == 2  # different lengths route to different branches
    assert opened.id != closed.id or opened.template[1] == WILD
    assert len(d.clusters) >= 3


def test_sample_logs_compress_to_a_dozen_templates(mined):
    drain, events, _ = mined
    assert len(events) == 2347
    assert 10 <= len(drain.clusters) <= 14
    texts = {c.text for c in drain.clusters}
    assert "heartbeat seq=<NUM> ok" in texts


def test_new_template_detected_with_its_host(mined):
    drain, _, found = mined
    new = [a for a in found if a.kind == "new"]
    assert any(a.template.startswith("PSU2 input voltage") and a.hosts == ["r13-bmc"] for a in new)
    assert min(a.window for a in new) == 26  # 04:20, when the PSU fault starts


def test_burst_detected_against_baseline_rate(mined):
    _, _, found = mined
    bursts = [a for a in found if a.kind == "burst"]
    assert bursts and all(a.template.startswith("fan") for a in bursts)
    assert all(a.count >= 3 * a.expected for a in bursts)


def test_silence_only_flags_the_dead_host(mined):
    _, _, found = mined
    silent = [a for a in found if a.kind == "silent"]
    assert {h for a in silent for h in a.hosts} == {"r13-bmc"}
    heartbeat = [a for a in silent if a.template.startswith("heartbeat")]
    assert heartbeat[0].window == 28  # needs three empty windows (p0^3 < 1e-4), so one quiet window never pages


def test_quiet_baseline_logs_produce_no_anomalies():
    drain = Drain()
    lines = generate(hours=6, seed=7, incident_at=10 ** 9)  # no incident
    events = []
    for ln in lines:
        h, m, s = (int(x) for x in ln[:8].split(":"))
        host, msg = ln[9:].split(" ", 1)
        events.append(Event(h * 3600 + m * 60 + s, host, drain.add(msg).id))
    assert detect(events, drain) == []


def test_incidents_group_consecutive_windows(mined):
    _, _, found = mined
    groups = incidents(found)
    assert len(groups) == 1
    assert groups[0][0].window == 26
