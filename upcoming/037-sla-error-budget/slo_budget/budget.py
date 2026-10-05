"""Core SLO math: allowed downtime, error budget, burn rate, SLA credits."""
from __future__ import annotations

from dataclasses import dataclass


def allowed_downtime_minutes(slo: float, days: float) -> float:
    """Minutes of full outage that fit inside the error budget for a time-based SLO."""
    return (1 - slo) * days * 24 * 60


def burn_rate(bad: float, total: float, slo: float) -> float:
    """How fast the budget is being spent: 1.0 means exactly on pace to use it all by window end."""
    if total <= 0:
        return 0.0
    return (bad / total) / (1 - slo)


@dataclass
class BudgetStatus:
    slo: float
    good: float
    total: float

    @property
    def sli(self) -> float:
        return self.good / self.total if self.total else 1.0

    @property
    def budget_events(self) -> float:
        return (1 - self.slo) * self.total

    @property
    def consumed(self) -> float:
        """Share of the error budget used (can exceed 1.0)."""
        bad = self.total - self.good
        return bad / self.budget_events if self.budget_events else 0.0

    @property
    def remaining(self) -> float:
        return 1 - self.consumed


def sla_credit_pct(availability: float, tiers: list[dict]) -> int:
    """Highest credit tier whose threshold the availability falls below."""
    owed = 0
    for tier in tiers:
        if availability < tier["below"]:
            owed = max(owed, int(tier["credit_pct"]))
    return owed


def nines_table(targets=(0.99, 0.995, 0.999, 0.9995, 0.9999)) -> list[tuple[float, float, float, float]]:
    """(target, minutes/30d, minutes/quarter, minutes/year)."""
    return [(t, allowed_downtime_minutes(t, 30), allowed_downtime_minutes(t, 91), allowed_downtime_minutes(t, 365))
            for t in targets]
