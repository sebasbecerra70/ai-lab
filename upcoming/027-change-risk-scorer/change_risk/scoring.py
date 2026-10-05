"""Score a change request on likelihood x impact, check timing and rollback, and recommend a CAB action."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .topology import Node, Outage, simulate, single_points_of_failure

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_RATE = 0.10
SOFTWARE_TYPES = {"config", "software-deploy", "firmware"}  # types where a staging rehearsal is possible


@dataclass
class Change:
    id: str
    title: str
    type: str
    targets: list[str]
    start: datetime
    end: datetime
    rollback_tested: bool
    rollback_minutes: int | None  # None = no rollback (irreversible)
    peer_reviewed: bool
    tested_in_staging: bool

    @staticmethod
    def from_dict(d: dict) -> "Change":
        rb = d.get("rollback", {})
        c = Change(d["id"], d["title"], d["type"], list(d["targets"]), datetime.fromisoformat(d["start"]),
                   datetime.fromisoformat(d["end"]), bool(rb.get("tested")), rb.get("minutes"),
                   bool(d.get("peer_reviewed")), bool(d.get("tested_in_staging")))
        if c.end <= c.start:
            raise ValueError(f"{c.id}: end must be after start")
        return c

    def overlaps(self, other: "Change") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass
class Assessment:
    change: Change
    failure_prob: float
    likelihood: int  # 1-5
    impact: int  # 1-5
    outage: Outage
    spofs: dict[str, list[str]]
    risk: int = 0  # likelihood x impact + timing penalty, 1-27
    blockers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    recommendation: str = ""


def load_changes(path: Path) -> list[Change]:
    return [Change.from_dict(d) for d in json.loads(path.read_text())]


def likelihood(c: Change, rates: dict[str, float]) -> tuple[float, int]:
    """Historical failure rate for the change type, adjusted for missing evidence. Returns (p, 1-5 band)."""
    p = rates.get(c.type, DEFAULT_RATE)
    if c.type in SOFTWARE_TYPES and not c.tested_in_staging:
        p *= 1.5
    if not c.peer_reviewed:
        p *= 1.3
    p *= 1 + 0.2 * (len(c.targets) - 1)
    p = min(p, 0.95)
    band = 1 if p < 0.03 else 2 if p < 0.06 else 3 if p < 0.10 else 4 if p < 0.15 else 5
    return p, band


def impact(topo: dict[str, Node], outage: Outage, spofs: dict[str, list[str]], targets: set[str] = frozenset()) -> int:
    """Worst case if the change fails and the targets go down. 5 = customers down ... 1 = target only."""
    if outage.customer_down(topo):
        return 5
    services = [n for n in outage.down if topo[n].kind == "service"]
    # the target itself being out is the plan; knock-on loss of shared infrastructure is the risk
    if len(services) > 1 or any(topo[n].kind in ("database", "storage", "network") for n in outage.down - targets):
        return 4
    if spofs or services:
        return 3  # one internal service down, or customers on a single path for the duration
    if outage.degraded or len(outage.down) > 1:
        return 2
    return 1


def in_window(c: Change, cal: dict) -> bool:
    for w in cal["maintenance_windows"]:
        if DAYS[c.start.weekday()] != w["weekday"]:
            continue
        day = c.start.date().isoformat()
        ws, we = datetime.fromisoformat(f"{day}T{w['start']}"), datetime.fromisoformat(f"{day}T{w['end']}")
        if ws <= c.start and c.end <= we:
            return True
    return False


def window_end(c: Change, cal: dict) -> datetime | None:
    for w in cal["maintenance_windows"]:
        if DAYS[c.start.weekday()] == w["weekday"]:
            end = datetime.fromisoformat(f"{c.start.date().isoformat()}T{w['end']}")
            if c.start < end:
                return end
    return None


def in_peak(c: Change, cal: dict) -> bool:
    peak = cal["peak_hours"]
    if DAYS[c.start.weekday()] not in peak["weekdays"]:
        return False
    day = c.start.date().isoformat()
    ps, pe = datetime.fromisoformat(f"{day}T{peak['start']}"), datetime.fromisoformat(f"{day}T{peak['end']}")
    return c.start < pe and ps < c.end


def freeze_hit(c: Change, cal: dict) -> str | None:
    for f in cal["freezes"]:
        if c.start < datetime.fromisoformat(f["end"]) and datetime.fromisoformat(f["start"]) < c.end:
            return f"{f['name']} freeze until {datetime.fromisoformat(f['end']).strftime('%a %d %b')}"
    return None


def assess(c: Change, topo: dict[str, Node], rates: dict[str, float], cal: dict) -> Assessment:
    outage = simulate(topo, set(c.targets))
    spofs = single_points_of_failure(topo, set(c.targets))
    p, lk = likelihood(c, rates)
    a = Assessment(c, p, lk, impact(topo, outage, spofs, set(c.targets)), outage, spofs)
    timing = 0
    if (freeze := freeze_hit(c, cal)):
        a.blockers.append(f"inside {freeze}")
    if not in_window(c, cal):
        timing = 2 if in_peak(c, cal) else 1
        a.conditions.append("move into a maintenance window" + (" (currently during peak hours)" if timing == 2 else ""))
    if c.rollback_minutes is None:
        a.conditions.append("no rollback: get a restore point and a go/no-go checkpoint signed off")
        if a.impact >= 4:
            a.blockers.append("irreversible change with service impact")
    else:
        if not c.rollback_tested:
            a.conditions.append(f"rehearse the {c.rollback_minutes}-min rollback before the window")
        end = window_end(c, cal)
        if end and c.end + timedelta(minutes=c.rollback_minutes) > end:
            a.conditions.append("rollback would overrun the window: start earlier or shorten scope")
    if not c.peer_reviewed:
        a.conditions.append("peer review of the implementation plan")
    for node, lost in sorted(spofs.items())[:3]:
        a.conditions.append(f"no work on {node} during the change (sole path for {', '.join(lost)})")
    a.risk = a.likelihood * a.impact + timing
    return a


def check_collisions(assessments: list[Assessment], topo: dict[str, Node]) -> None:
    """Overlapping changes are simulated together: two safe changes can add up to an outage."""
    for i, a in enumerate(assessments):
        for b in assessments[i + 1:]:
            if not a.change.overlaps(b.change):
                continue
            joint = simulate(topo, set(a.change.targets) | set(b.change.targets))
            extra = set(joint.customer_down(topo)) - set(a.outage.customer_down(topo)) - set(b.outage.customer_down(topo))
            for x, y in ((a, b), (b, a)):
                if extra:
                    x.blockers.append(f"overlaps {y.change.id}: together they take down {', '.join(sorted(extra))}")
                else:
                    x.conditions.append(f"overlaps {y.change.id} (no joint outage, but share the bridge call)")


def recommend(a: Assessment) -> str:
    c = a.change
    if a.blockers:
        a.recommendation = "REJECT / RESCHEDULE"
    elif a.risk >= 20:
        a.recommendation = "REJECT: reduce risk first"
    elif a.risk >= 12:
        a.recommendation = "CAB REVIEW"
    elif a.conditions:
        a.recommendation = "APPROVE WITH CONDITIONS"
    elif a.risk <= 6 and c.type == "config" and c.tested_in_staging and c.rollback_tested:
        a.recommendation = "STANDARD (pre-approved)"  # low-risk, repeatable: skip the CAB next time
    else:
        a.recommendation = "APPROVE"
    return a.recommendation


def score_all(changes: list[Change], topo: dict[str, Node], rates: dict[str, float], cal: dict) -> list[Assessment]:
    seen = set()
    for c in changes:
        if c.id in seen:
            raise ValueError(f"duplicate change id {c.id}")
        seen.add(c.id)
    out = [assess(c, topo, rates, cal) for c in changes]
    check_collisions(out, topo)
    for a in out:
        recommend(a)
    return sorted(out, key=lambda a: (-bool(a.blockers), -a.risk, a.change.id))
