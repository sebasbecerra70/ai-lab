"""The deal desk rulebook: approval ladder, allowances, margin floors, precedent and non-standard terms."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Deal:
    id: str
    customer: str
    segment: str
    product: str
    seats: int
    list_price_per_seat: float
    discount: float          # requested, in percent
    term_years: int
    annual_prepay: bool
    competitor: str | None
    non_standard_terms: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def list_arr(self) -> float:
        return self.seats * self.list_price_per_seat

    def net_arr(self, discount: float | None = None) -> float:
        d = self.discount if discount is None else discount
        return self.list_arr * (1 - d / 100)


@dataclass
class Finding:
    rule: str
    detail: str
    route: str | None = None
    blocking: bool = False


@dataclass
class Decision:
    deal: Deal
    status: str                    # auto-approve | escalate | reject
    pricing_role: str
    approvers: list[str]
    allowances: dict[str, float]
    effective_discount: float
    margin: float
    findings: list[Finding]
    give_gets: list[str]


def load_policy(path: Path) -> dict:
    return json.loads(path.read_text())


def load_deals(path: Path) -> list[Deal]:
    return [Deal(**d) for d in json.loads(path.read_text())]


def allowances_for(deal: Deal, policy: dict, term_years: int | None = None, prepay: bool | None = None) -> dict:
    """Points of discount the policy 'gives back' for terms that are worth money to us."""
    term = deal.term_years if term_years is None else term_years
    pre = deal.annual_prepay if prepay is None else prepay
    a = policy["allowances"]
    out = {}
    if term >= 3:
        out["3-year term"] = a["multi_year_3"]
    if pre:
        out["annual prepay"] = a["annual_prepay"]
    if deal.competitor:
        out[f"displacing {deal.competitor}"] = a["competitive_displacement"]
    return out


def role_for(effective: float, policy: dict) -> str:
    return next(step["role"] for step in policy["ladder"] if effective <= step["max_discount"])


def rank(role: str, policy: dict) -> int:
    roles = [s["role"] for s in policy["ladder"]]
    return roles.index(role)


def margin(deal: Deal, policy: dict, discount: float | None = None) -> float:
    net_per_seat = deal.list_price_per_seat * (1 - (deal.discount if discount is None else discount) / 100)
    return 1 - policy["cost_per_seat_year"][deal.product] / net_per_seat if net_per_seat > 0 else float("-inf")


def evaluate(deal: Deal, policy: dict, prior_discount: float | None = None, explore: bool = True) -> Decision:
    """Apply every rule. The pricing approver comes from the ladder; other rules can raise it or add side
    approvers (Legal, Finance). Blocking findings reject the deal as structured."""
    allow = allowances_for(deal, policy)
    effective = max(0.0, deal.discount - sum(allow.values()))
    role = role_for(effective, policy)
    findings: list[Finding] = []

    def at_least(r: str, rule: str, detail: str) -> None:
        nonlocal role
        findings.append(Finding(rule, detail, r))
        if rank(r, policy) > rank(role, policy):
            role = r

    if deal.net_arr() >= policy["large_deal_arr"]:
        at_least(policy["large_deal_min_role"], "large deal",
                 f"net ARR ${deal.net_arr():,.0f} is at or above ${policy['large_deal_arr']:,.0f}")
    m = margin(deal, policy)
    if m < policy["margin_hard_floor"]:
        findings.append(Finding("margin hard floor", f"gross margin {m:.0%} is below the "
                                f"{policy['margin_hard_floor']:.0%} hard floor", "CFO", blocking=True))
    elif m < policy["margin_floor"]:
        at_least("CFO", "margin floor", f"gross margin {m:.0%} is below the {policy['margin_floor']:.0%} floor")
    if deal.term_years > policy["max_term_years_without_cfo"]:
        at_least("CFO", "long term", f"{deal.term_years}-year price lock")
    if prior_discount is not None and deal.discount - prior_discount > policy["precedent_jump_pts"]:
        at_least("Sales Manager", "precedent", f"{deal.discount:.0f}% vs {prior_discount:.0f}% on the last deal "
                 "with this customer; the next renewal will anchor on it")

    side: list[str] = []
    for term in deal.non_standard_terms:
        rule = policy["non_standard_terms"].get(term)
        if rule is None:
            findings.append(Finding("unknown term", f"'{term}' is not in the playbook", "Legal"))
            side.append("Legal")
            continue
        findings.append(Finding(f"non-standard: {term}", rule["note"], rule["route"], rule.get("reject", False)))
        side.append(rule["route"])

    approvers = [role] + [s for s in dict.fromkeys(side) if s != role]
    if any(f.blocking for f in findings):
        status = "reject"
    elif role == policy["ladder"][0]["role"] and not side and not findings:
        status = "auto-approve"
    else:
        status = "escalate"
    d = Decision(deal, status, role, approvers, allow, effective, m, findings, [])
    if explore:
        d.give_gets = give_gets(d, policy, prior_discount)
    return d


def lower_level_discount(d: Decision, policy: dict, prior: float | None = None) -> float | None:
    """The deepest discount, on the current terms, that someone below the current pricing approver can sign.
    Re-runs the whole rulebook at each step, so margin and precedent rules are respected too."""
    if rank(d.pricing_role, policy) == 0:
        return None
    for x in range(int(d.deal.discount) - 1, -1, -1):
        alt = evaluate(replace(d.deal, discount=float(x)), policy, prior, explore=False)
        if rank(alt.pricing_role, policy) < rank(d.pricing_role, policy):
            return float(x)
    return None


def give_gets(d: Decision, policy: dict, prior: float | None = None) -> list[str]:
    """Trades the AE can offer instead of escalating: terms that lower the approval level for the same discount,
    and the deepest discount the next level down can sign today."""
    deal, out = d.deal, []
    if d.status == "reject" or rank(d.pricing_role, policy) == 0:
        return out
    options = []
    if deal.term_years < 3:
        options.append(("a 3-year term", dict(term_years=3)))
    if not deal.annual_prepay:
        options.append(("annual prepay", dict(annual_prepay=True)))
    if len(options) == 2:
        options.append(("a 3-year term with annual prepay", dict(term_years=3, annual_prepay=True)))
    best_single = rank(d.pricing_role, policy)
    for i, (label, kw) in enumerate(options):
        r = evaluate(replace(deal, **kw), policy, prior, explore=False).pricing_role
        combo = i == 2
        if rank(r, policy) < (best_single if combo else rank(d.pricing_role, policy)):
            out.append(f"with {label}, {deal.discount:.0f}% needs only {r}")
        if not combo:
            best_single = min(best_single, rank(r, policy))
    x = lower_level_discount(d, policy, prior)
    if x is not None:
        role = evaluate(replace(deal, discount=x), policy, prior, explore=False).pricing_role
        out.append(f"{role} can approve {x:.0f}% on the current terms "
                   f"(${deal.net_arr(x) - deal.net_arr():,.0f} more net ARR a year)")
    return out
