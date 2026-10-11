"""Dedupe alerts, correlate them into incidents through the rack topology, and assign severity."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

RAW_WEIGHT = {"warning": 1, "major": 2, "critical": 3}
AVAILABILITY_CHECKS = {"host_down", "http_5xx"}
INFRA_CATEGORY = {"pdu_input": "power", "pdu_load": "power", "supply_temp": "cooling", "interface_flap": "network"}
INFRA_POINTS = {"power": 3, "cooling": 3, "network": 2}


@dataclass(frozen=True)
class Alert:
    seconds: int
    source: str
    host: str
    check: str
    severity: str
    message: str


@dataclass
class AlertGroup:
    """One fingerprint (host + check) seen repeatedly. 12 identical disk warnings are one problem."""
    host: str
    check: str
    alerts: list[Alert] = field(default_factory=list)

    @property
    def first(self) -> int:
        return self.alerts[0].seconds

    @property
    def last(self) -> int:
        return self.alerts[-1].seconds

    @property
    def severity(self) -> str:
        return max((a.severity for a in self.alerts), key=RAW_WEIGHT.get)


@dataclass
class Incident:
    groups: list[AlertGroup]
    root_cause: str
    severity: str = "SEV4"
    points: int = 0
    services: list[str] = field(default_factory=list)

    @property
    def first(self) -> int:
        return min(g.first for g in self.groups)

    @property
    def alert_count(self) -> int:
        return sum(len(g.alerts) for g in self.groups)


def parse_time(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def fmt_time(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def load_alerts(path: str | Path) -> list[Alert]:
    raw = json.loads(Path(path).read_text())
    alerts = [Alert(parse_time(a["time"]), a["source"], a["host"], a["check"], a["severity"], a["message"])
              for a in raw]
    return sorted(alerts, key=lambda a: a.seconds)


def fingerprint(alert: Alert) -> tuple[str, str]:
    # Host + check, not message: the message changes on every repeat ("86%" -> "87%", "up" -> "down").
    return alert.host, alert.check


def dedupe(alerts: list[Alert], gap_seconds: int = 1800) -> list[AlertGroup]:
    open_groups: dict[tuple[str, str], AlertGroup] = {}
    groups: list[AlertGroup] = []
    for a in alerts:
        key = fingerprint(a)
        g = open_groups.get(key)
        if g is None or a.seconds - g.last > gap_seconds:
            g = AlertGroup(a.host, a.check)
            open_groups[key] = g
            groups.append(g)
        g.alerts.append(a)
    return groups


class Topology:
    def __init__(self, data: dict):
        self.hosts, self.racks = data["hosts"], data["racks"]

    @classmethod
    def load(cls, path: str | Path) -> "Topology":
        return cls(json.loads(Path(path).read_text()))

    def upstream(self, host: str) -> set[str]:
        """Shared infrastructure a host depends on. An infra device's own alerts point to itself."""
        if host not in self.hosts:
            return {host}
        rack = self.racks[self.hosts[host]["rack"]]
        return {rack["pdu"], rack["switch"], rack["crac"]}

    def service(self, host: str) -> tuple[str, int] | None:
        h = self.hosts.get(host)
        return (h["service"], h["tier"]) if h else None


def correlate(groups: list[AlertGroup], topo: Topology, window_seconds: int = 300) -> list[Incident]:
    """Union groups that overlap in time AND share a host or an upstream component that is itself alerting.

    Requiring the shared component to be alerting stops every host in a hall from merging just because
    they share a CRAC unit that is fine.
    """
    alerting_infra = {g.host for g in groups if g.host not in topo.hosts}
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(groups):
        for j in range(i + 1, len(groups)):
            b = groups[j]
            overlap = a.first <= b.last + window_seconds and b.first <= a.last + window_seconds
            if not overlap:
                continue
            shared = topo.upstream(a.host) & topo.upstream(b.host) & alerting_infra
            if a.host == b.host or shared:
                parent[find(i)] = find(j)

    clusters: dict[int, list[AlertGroup]] = {}
    for i, g in enumerate(groups):
        clusters.setdefault(find(i), []).append(g)
    incidents = []
    for members in clusters.values():
        members.sort(key=lambda g: g.first)
        infra = [g for g in members if g.host in alerting_infra]
        # Root cause: the alerting infrastructure device, else the earliest alert in the cluster.
        root = infra[0].host if infra else members[0].host
        incidents.append(Incident(members, root))
    return sorted(incidents, key=lambda inc: inc.first)


def score(incident: Incident, topo: Topology) -> Incident:
    hosts = {g.host for g in incident.groups if g.host in topo.hosts}
    services = {topo.service(h) for h in hosts}
    tier1_down = any(g.check in AVAILABILITY_CHECKS and topo.service(g.host)[1] == 1
                     for g in incident.groups if g.host in topo.hosts)
    infra = {INFRA_CATEGORY[g.check] for g in incident.groups if g.check in INFRA_CATEGORY}
    points = max(RAW_WEIGHT[g.severity] for g in incident.groups)
    points += 3 if tier1_down else (1 if any(t == 1 for _, t in services) else 0)
    points += min(3, max(0, len(hosts) - 1))
    points += max((INFRA_POINTS[c] for c in infra), default=0)
    points += 1 if any(len(g.alerts) >= 5 and g.check not in INFRA_CATEGORY for g in incident.groups) else 0
    incident.points = points
    incident.severity = "SEV1" if points >= 8 else "SEV2" if points >= 5 else "SEV3" if points >= 3 else "SEV4"
    incident.services = sorted(f"{s} (tier {t})" for s, t in services)
    return incident


def triage(alerts: list[Alert], topo: Topology) -> list[Incident]:
    incidents = [score(i, topo) for i in correlate(dedupe(alerts), topo)]
    return sorted(incidents, key=lambda i: (i.severity, i.first))
