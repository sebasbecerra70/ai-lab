"""The deal desk agent: gather context, apply policy, price the win-rate trade-off, draft the approver memo
with an LLM, and verify the memo against the facts before anyone sees it."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import LLMClient
from .policy import Deal, Decision, evaluate, lower_level_discount
from .winrate import WinModel, prior_discount

SYSTEM = (
    "You are a deal desk analyst writing a short approval memo for a sales executive. Use only the numbers in "
    "FACTS, formatted the same way. State the recommendation and every required approver exactly as given; you "
    "cannot change the decision. Plain text, under 150 words."
)


@dataclass
class Review:
    decision: Decision
    facts: dict
    memo: str
    memo_issues: list[str]


def counter_discount(decision: Decision, policy: dict, prior: float | None = None) -> float:
    """The deepest discount one approval level lower could sign on current terms (or the request if none)."""
    x = lower_level_discount(decision, policy, prior)
    return decision.deal.discount if x is None else x


def build_facts(d: Decision, model: WinModel | None, policy: dict, prior: float | None = None) -> dict:
    deal = d.deal
    facts = {
        "id": deal.id, "customer": deal.customer, "discount_pct": round(deal.discount),
        "list_arr": round(deal.list_arr), "net_arr": round(deal.net_arr()), "term_years": deal.term_years,
        "tcv": round(deal.net_arr() * deal.term_years), "margin_pct": round(100 * d.margin),
        "allowances": d.allowances, "effective_discount_pct": round(d.effective_discount),
        "status": d.status, "approvers": d.approvers,
        "findings": [f"{f.rule}: {f.detail}" + (f" -> {f.route}" if f.route else "") for f in d.findings],
        "give_gets": d.give_gets,
    }
    if model is not None:
        c = counter_discount(d, policy, prior)
        comp = deal.competitor is not None
        p_req, p_ctr = model.p_win(deal.discount, comp, deal.segment), model.p_win(c, comp, deal.segment)
        facts.update(win_at_request_pct=round(100 * p_req), win_at_counter_pct=round(100 * p_ctr),
                     counter_discount_pct=round(c), expected_arr_request=round(p_req * deal.net_arr()),
                     expected_arr_counter=round(p_ctr * deal.net_arr(c)))
    return facts


def _numbers(value) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", value)]
    if isinstance(value, dict):
        return [n for k, v in value.items() for n in _numbers(k) + _numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    return []


def verify_memo(memo: str, facts: dict) -> list[str]:
    """Every number in the memo must come from the facts, and the decision and approvers must be stated as
    decided. A memo that invents a margin or drops Legal from the approver list never reaches an executive."""
    allowed = set(_numbers(facts))
    issues = []
    for tok in re.findall(r"\d[\d,]*(?:\.\d+)?", memo):
        x = float(tok.replace(",", ""))
        if not any(abs(x - a) <= 0.5 for a in allowed):
            issues.append(f"number not in facts: {tok}")
    for role in facts["approvers"]:
        if role not in memo:
            issues.append(f"approver missing: {role}")
    if facts["status"] not in memo:
        issues.append(f"decision not stated: {facts['status']}")
    return issues


def template_memo(facts: dict) -> str:
    return (f"{facts['customer']} ({facts['id']}): {facts['status']}, {facts['discount_pct']}% requested, "
            f"approvers: {', '.join(facts['approvers'])}. " + " ".join(facts["findings"]))


def review(deal: Deal, policy: dict, llm: LLMClient, model: WinModel | None = None,
           history: list[dict] | None = None) -> Review:
    prior = prior_discount(history, deal.customer) if history else None
    d = evaluate(deal, policy, prior)
    facts = build_facts(d, model, policy, prior)
    memo = llm.complete(SYSTEM, f"Write the approval memo.\nNOTES FROM AE: {deal.notes}\nFACTS:\n{json.dumps(facts)}")
    issues = verify_memo(memo, facts)
    if issues:
        memo = template_memo(facts)  # fall back to a plain memo that is correct by construction
    return Review(d, facts, memo, issues)
