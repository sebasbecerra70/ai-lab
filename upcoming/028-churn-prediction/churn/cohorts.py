"""Load accounts and build the cohort retention triangle."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Account:
    account_id: str
    cohort: int  # signup month index, 1 = oldest
    plan: str
    seats: int
    billing: str
    onboarding_completed: int
    active_days_first30: int
    integrations_first30: int
    support_tickets_first30: int
    churn_month: int | None  # months after signup when the account cancelled; None = still active


def load_accounts(path: Path) -> list[Account]:
    with open(path, newline="") as f:
        return [Account(r["account_id"], int(r["cohort"]), r["plan"], int(r["seats"]), r["billing"],
                        int(r["onboarding_completed"]), int(r["active_days_first30"]), int(r["integrations_first30"]),
                        int(r["support_tickets_first30"]), int(r["churn_month"]) if r["churn_month"] else None)
                for r in csv.DictReader(f)]


def months_observed(a: Account, latest_cohort: int) -> int:
    """The newest cohort has one month of history, the one before it two, and so on."""
    return latest_cohort + 1 - a.cohort


def retention_triangle(accounts: list[Account]) -> dict[int, list[float]]:
    """cohort -> [share still active after month 1, 2, ...], only for months the cohort has lived through."""
    latest = max(a.cohort for a in accounts)
    table: dict[int, list[float]] = {}
    for c in sorted({a.cohort for a in accounts}):
        members = [a for a in accounts if a.cohort == c]
        age = latest + 1 - c
        table[c] = [sum(a.churn_month is None or a.churn_month > m for a in members) / len(members)
                    for m in range(1, age + 1)]
    return table


def blended_curve(accounts: list[Account]) -> list[float]:
    """Kaplan-Meier retention across all cohorts: multiply month-by-month survival among accounts at risk.

    Pooling "% active at month N" over the cohorts old enough to have reached month N would make the tail
    jump around, because only one or two cohorts are left there. Chaining conditional survival uses every
    cohort for every month it has observed, and the curve can only go down.
    """
    latest = max(a.cohort for a in accounts)
    curve, survival = [], 1.0
    for m in range(1, latest + 1):
        at_risk = [a for a in accounts if months_observed(a, latest) >= m and (a.churn_month is None or a.churn_month >= m)]
        churned = sum(a.churn_month == m for a in at_risk)
        survival *= 1 - churned / len(at_risk)
        curve.append(survival)
    return curve
