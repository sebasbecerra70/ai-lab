"""Multi-window, multi-burn-rate alerting (the SRE workbook pattern) replayed over a timeline."""
from __future__ import annotations

from dataclasses import dataclass

from .budget import burn_rate
from .timeline import Incident, Timeline


@dataclass(frozen=True)
class AlertRule:
    name: str
    severity: str  # page | ticket
    long_min: int
    short_min: int
    threshold: float  # burn-rate multiple

    @property
    def budget_spent_at_fire(self) -> float:
        """Share of a 30-day budget consumed by the time the long window trips."""
        return self.threshold * self.long_min / (30 * 24 * 60)


# 2% of budget in 1h, 5% in 6h, 10% in 3d: the standard starting point.
DEFAULT_RULES = [
    AlertRule("fast-burn", "page", 60, 5, 14.4),
    AlertRule("medium-burn", "page", 360, 30, 6.0),
    AlertRule("slow-burn", "ticket", 4320, 360, 1.0),
]


@dataclass
class AlertEvent:
    rule: AlertRule
    fired_at: int
    resolved_at: int


def replay(tl: Timeline, slo: float, rules=DEFAULT_RULES, step: int = 1) -> list[AlertEvent]:
    """Evaluate every rule each `step` minutes; an alert fires when BOTH windows exceed the
    threshold and resolves when either drops below (the short window gives fast reset)."""
    events: list[AlertEvent] = []
    for rule in rules:
        open_at = None
        for m in range(step, len(tl) + 1, step):
            long_br = burn_rate(*tl.window(m, rule.long_min), slo)
            short_br = burn_rate(*tl.window(m, rule.short_min), slo)
            firing = long_br >= rule.threshold and short_br >= rule.threshold
            if firing and open_at is None:
                open_at = m
            elif not firing and open_at is not None:
                events.append(AlertEvent(rule, open_at, m))
                open_at = None
        if open_at is not None:
            events.append(AlertEvent(rule, open_at, len(tl)))
    return sorted(events, key=lambda e: (e.fired_at, e.rule.name))


@dataclass
class Detection:
    incident: Incident
    first_alert: AlertEvent | None

    @property
    def delay_min(self) -> int | None:
        return None if self.first_alert is None else self.first_alert.fired_at - self.incident.start


def match_incidents(incidents: list[Incident], events: list[AlertEvent], grace_min: int = 360) -> list[Detection]:
    """First alert that fires during an incident (or within a grace period after it)."""
    out = []
    for inc in incidents:
        hit = next((e for e in events if inc.start <= e.fired_at <= inc.end + grace_min), None)
        out.append(Detection(inc, hit))
    return out
