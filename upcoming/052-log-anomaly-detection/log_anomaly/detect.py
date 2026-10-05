"""Count template occurrences per time window and flag three kinds of anomaly against a baseline:
new event types, bursts of known ones, and regular per-host events that went silent."""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .drain import Drain

LINE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}) (\S+) (.*)$")


@dataclass
class Event:
    sec: int
    host: str
    cluster: int


@dataclass
class Anomaly:
    window: int
    kind: str          # new | burst | silent
    cluster: int
    template: str
    count: int
    expected: float
    score: float
    hosts: list[str]


def parse(path: Path, drain: Drain) -> list[Event]:
    events = []
    for line in path.read_text().splitlines():
        m = LINE.match(line)
        if not m:
            continue
        h, mi, s, host, msg = m.groups()
        events.append(Event(int(h) * 3600 + int(mi) * 60 + int(s), host, drain.add(msg).id))
    return events


def detect(events: list[Event], drain: Drain, window: int = 600, baseline_until: int = 4 * 3600,
           z_burst: float = 4.0, min_ratio: float = 3.0, alpha: float = 1e-4) -> list[Anomaly]:
    n_windows = max(e.sec for e in events) // window + 1
    n_base = baseline_until // window
    counts: dict[int, Counter] = defaultdict(Counter)          # window -> cluster -> count
    host_counts: dict[tuple[int, str], Counter] = defaultdict(Counter)  # (cluster, host) -> window -> count
    hosts_in: dict[tuple[int, int], set[str]] = defaultdict(set)
    for e in events:
        w = e.sec // window
        counts[w][e.cluster] += 1
        host_counts[(e.cluster, e.host)][w] += 1
        hosts_in[(w, e.cluster)].add(e.host)

    seen_in_baseline = {c for w in range(n_base) for c in counts[w]}
    out: list[Anomaly] = []
    for w in range(n_base, n_windows):
        for c, x in counts[w].items():
            tpl = drain.clusters[c].text
            hosts = sorted(hosts_in[(w, c)])
            if c not in seen_in_baseline:
                out.append(Anomaly(w, "new", c, tpl, x, 0.0, float("inf"), hosts))
                continue
            base = [counts[b][c] for b in range(n_base)]
            mu = statistics.mean(base)
            # Poisson-style z with a +1 floor so rare templates don't explode on a single extra line
            z = (x - mu) / math.sqrt(mu + 1)
            if z >= z_burst and x >= min_ratio * max(mu, 1):
                out.append(Anomaly(w, "burst", c, tpl, x, mu, z, hosts))
    # silence: a (template, host) pair whose run of empty windows would be very unlikely given how often it
    # was empty in the baseline. A 5-minute heartbeat (never empty) trips after 2 windows; a chatty but
    # irregular sensor needs a longer run, so random quiet spells don't page anyone.
    for (c, host), per_w in host_counts.items():
        zeros = sum(per_w[b] == 0 for b in range(n_base))
        p0 = (zeros + 0.5) / (n_base + 1)
        mu = statistics.mean(per_w[b] for b in range(n_base))
        run = 0
        for w in range(n_base, n_windows):
            run = run + 1 if per_w[w] == 0 else 0
            if run and p0 ** run < alpha:
                out.append(Anomaly(w, "silent", c, drain.clusters[c].text, 0, mu, -math.log10(p0 ** run), [host]))
    out.sort(key=lambda a: (a.window, {"new": 0, "silent": 1, "burst": 2}[a.kind], -a.score))
    return out


def incidents(anomalies: list[Anomaly], gap: int = 1) -> list[list[Anomaly]]:
    """Group anomalies in consecutive windows into incidents (one page, not twenty)."""
    groups: list[list[Anomaly]] = []
    for a in sorted(anomalies, key=lambda a: a.window):
        if groups and a.window - groups[-1][-1].window <= gap:
            groups[-1].append(a)
        else:
            groups.append([a])
    return groups
