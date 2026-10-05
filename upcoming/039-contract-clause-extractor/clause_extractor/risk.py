"""Risk policy: turn extracted clause fields into flags a deal team can act on."""
from __future__ import annotations

from dataclasses import dataclass

from .rules import Clause

SEVERITY_POINTS = {"high": 3, "medium": 2, "low": 1}


@dataclass
class Policy:
    max_renewal_notice_days: int = 60
    min_liability_cap_months: int = 12
    max_payment_days: int = 45  # when we are the one waiting to be paid
    home_jurisdictions: tuple[str, ...] = ("Delaware", "New York")


@dataclass
class RiskFlag:
    severity: str
    clause: int
    message: str


def assess(clauses: list[Clause], role: str, policy: Policy = Policy()) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    me = role.lower()
    for c in clauses:
        f = c.fields
        if c.type == "renewal" and f.get("auto_renew"):
            n = f.get("notice_days")
            if n and n > policy.max_renewal_notice_days:
                flags.append(RiskFlag("medium", c.number, f"auto-renews with {n}-day notice window (policy max {policy.max_renewal_notice_days})"))
            else:
                flags.append(RiskFlag("low", c.number, "auto-renewal: add to the renewal calendar"))
        elif c.type == "termination":
            parties = f.get("convenience_parties", [])
            others = [p for p in parties if p not in ("either", me)]
            if f.get("any_time") and others:
                flags.append(RiskFlag("high", c.number, f"{others[0]} can terminate at any time without notice"))
            elif others and "either" not in parties and me not in parties:
                flags.append(RiskFlag("high", c.number, f"only {others[0]} can terminate for convenience"))
            elif others and me in parties:
                flags.append(RiskFlag("low", c.number, "asymmetric convenience notice periods"))
        elif c.type == "liability":
            if f.get("we_are_uncapped"):
                flags.append(RiskFlag("high", c.number, "our liability is uncapped"))
            cap = f.get("cap_months")
            if cap is not None and cap < policy.min_liability_cap_months:
                flags.append(RiskFlag("medium", c.number, f"counterparty cap only {cap} months of fees (policy min {policy.min_liability_cap_months})"))
        elif c.type == "indemnification":
            if not f.get("mutual") and f.get("indemnitor") == me:
                sev = "high" if f.get("broad_scope") else "medium"
                flags.append(RiskFlag(sev, c.number, "one-way indemnity owed by us" + (" with broad scope" if f.get("broad_scope") else "")))
        elif c.type == "payment":
            d = f.get("days")
            if f.get("we_are_payee") and d and d > policy.max_payment_days:
                flags.append(RiskFlag("medium", c.number, f"{d}-day payment terms (policy max {policy.max_payment_days})"))
        elif c.type == "governing_law":
            j = f.get("jurisdiction")
            if j and j not in policy.home_jurisdictions:
                flags.append(RiskFlag("medium", c.number, f"foreign governing law: {j}"))
    return sorted(flags, key=lambda r: (-SEVERITY_POINTS[r.severity], r.clause))


def risk_score(flags: list[RiskFlag]) -> int:
    return sum(SEVERITY_POINTS[f.severity] for f in flags)
