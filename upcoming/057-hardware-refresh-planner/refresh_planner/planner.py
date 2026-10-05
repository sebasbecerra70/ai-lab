"""Year-by-year refresh plans under an annual capex budget, for three policies."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from .model import Assumptions, Cohort, cohort_opex, npv_of_refresh, platform_for, refresh_capex, replacement

TRANCHE = 100      # refresh big cohorts in pieces so one cohort can't eat a whole year's budget
BUDGET_UNIT = 10_000


@dataclass
class Action:
    cohort: str
    servers: int
    platform: str
    new_servers: int
    capex: float
    npv: float
    reason: str


@dataclass
class YearPlan:
    year: int
    budget: float
    actions: list[Action] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    opex: float = 0.0

    @property
    def spent(self) -> float:
        return sum(x.capex for x in self.actions)


@dataclass
class PlanResult:
    policy: str
    years: list[YearPlan]
    pv_cost: float          # opex + depreciation of new hardware, discounted
    pv_cash: float          # opex + capex as paid, discounted
    exit_opex: float
    exit_fleet: list[Cohort]

    @property
    def over_budget(self) -> list[int]:
        return [y.year for y in self.years if y.spent > y.budget + 1]


def tranches(c: Cohort) -> list[Cohort]:
    k = math.ceil(c.servers / TRANCHE)
    sizes = [c.servers // k + (1 if i < c.servers % k else 0) for i in range(k)]
    return [replace(c, servers=s) for s in sizes]


def knapsack(items: list[tuple[object, float, float]], budget: float) -> list[object]:
    """0/1 knapsack by dynamic programming: pick items (key, cost, value) maximizing value within budget.
    Costs are rounded up to BUDGET_UNIT so the table stays small, which can only under-spend."""
    cap = int(budget // BUDGET_UNIT)
    best = [(0.0, [])] * (cap + 1)
    for key, cost, value in items:
        w = math.ceil(cost / BUDGET_UNIT)
        if value <= 0 or w > cap:
            continue
        nxt = list(best)
        for b in range(w, cap + 1):
            v = best[b - w][0] + value
            if v > nxt[b][0]:
                nxt[b] = (v, best[b - w][1] + [key])
        best = nxt
    return best[cap][1]


def mandatory(c: Cohort, a: Assumptions) -> bool:
    """Must go this year: next year it would run past vendor end of support."""
    return c.age + 1 >= a.end_of_support_age


def choose_tco(fleet: list[Cohort], year: int, budget: float, a: Assumptions) -> tuple[list[tuple[Cohort, str]], list[str]]:
    """Positive-NPV tranches, picked by knapsack. A tranche is deferred when waiting a year for the next
    platform is worth more than refreshing now (the option value of the roadmap)."""
    items, deferred = [], []
    for c in fleet:
        if mandatory(c, a):
            continue
        for i, t in enumerate(tranches(c)):
            now = npv_of_refresh(t, year, a)
            # never defer into a forced refresh: that just piles capex onto next year's budget
            waitable = not mandatory(replace(c, age=c.age + 1), a)
            if waitable and platform_for(year + 1, a) != platform_for(year, a) and \
                    npv_of_refresh(t, year, a, 1) > max(now, 0.0):
                deferred.append(c.name)
                break
            if now <= 0:
                break
            items.append(((c.name, i, t), refresh_capex(t, platform_for(year, a), a), now))
    picked = knapsack(items, budget)
    return [(t, "positive NPV") for _, _, t in picked], deferred


def choose_age(fleet: list[Cohort], year: int, budget: float, a: Assumptions, max_age: int = 5):
    """The common rule of thumb: replace anything at or past `max_age`, oldest first, until the money runs out."""
    out = []
    for c in sorted(fleet, key=lambda c: -c.age):
        if c.age < max_age or mandatory(c, a):
            continue
        for t in tranches(c):
            cost = refresh_capex(t, platform_for(year, a), a)
            if cost > budget:
                break
            budget -= cost
            out.append((t, f"age {c.age} >= {max_age}"))
    return out, []


def choose_none(fleet, year, budget, a):
    return [], []


POLICIES = {"run-to-EOS": choose_none, "5-year age": choose_age, "TCO-optimized": choose_tco}


def run(fleet: list[Cohort], a: Assumptions, policy: str) -> PlanResult:
    """Simulate the horizon: each year do the mandatory end-of-support refreshes, let the policy spend the rest
    of the budget, pay a year of opex, then age everything by a year."""
    chooser = POLICIES[policy]
    fleet = list(fleet)
    years, pv, cash = [], 0.0, 0.0
    bought: list[tuple[int, float, int]] = []   # (year, capex, useful life)
    for y in range(a.horizon_years):
        budget = a.annual_budget[min(y, len(a.annual_budget) - 1)]
        plan = YearPlan(y + 1, budget)
        p = platform_for(y, a)
        picks = [(c, "end of support") for c in fleet if mandatory(c, a)]
        left = budget - sum(refresh_capex(c, p, a) for c, _ in picks)
        rest = [c for c in fleet if not mandatory(c, a)]
        more, plan.deferred = chooser(rest, y, max(left, 0.0), a)
        picks += more
        for t, reason in picks:
            plan.actions.append(Action(t.name, t.servers, p.name, replacement(t, p, y).servers,
                                       refresh_capex(t, p, a), npv_of_refresh(t, y, a), reason))
        fleet = _apply(fleet, picks, p, y)
        plan.opex = sum(cohort_opex(c, a) for c in fleet)
        bought.append((y, plan.spent, p.warranty_years))
        # Charge capex as straight-line depreciation over the platform's life. Comparing cash spend over a
        # fixed horizon would reward any policy that pushes purchases past the end of it.
        depreciation = sum(cost / life for when, cost, life in bought if y - when < life)
        disc = (1 + a.discount_rate) ** -y
        pv += (plan.opex + depreciation) * disc
        cash += (plan.opex + plan.spent) * disc
        years.append(plan)
        fleet = [replace(c, age=c.age + 1) for c in fleet]
    return PlanResult(policy, years, pv, cash, sum(cohort_opex(c, a) for c in fleet), fleet)


def _apply(fleet: list[Cohort], picks: list[tuple[Cohort, str]], p, year: int) -> list[Cohort]:
    removed: dict[str, int] = {}
    for t, _ in picks:
        removed[t.name] = removed.get(t.name, 0) + t.servers
    out = []
    for c in fleet:
        left = c.servers - removed.get(c.name, 0)
        if left > 0:
            out.append(replace(c, servers=left))
        if c.name in removed:
            out.append(replacement(replace(c, servers=removed[c.name]), p, year))
    return out
