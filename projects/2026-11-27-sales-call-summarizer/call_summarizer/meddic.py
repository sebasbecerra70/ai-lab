"""Extract MEDDIC with verified evidence, then score deal health and suggest next actions."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMClient
from .transcript import Call, quote_in

FIELDS = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "identify_pain", "champion"]
WEIGHTS = {"metrics": 15, "economic_buyer": 20, "decision_criteria": 15, "decision_process": 15,
           "identify_pain": 20, "champion": 15}
CREDIT = {"confirmed": 1.0, "partial": 0.4, "missing": 0.0, "unverified": 0.0}
# fields a deal should have confirmed by each stage; gaps against the stage matter more than raw gaps
STAGE_EXPECTS = {"Discovery": ["identify_pain"], "Evaluation": ["identify_pain", "metrics", "economic_buyer", "decision_criteria"],
                 "Negotiation": FIELDS}
NEXT_ACTION = {
    "metrics": "Quantify the pain: ask what the problem cost last year in dollars or hours.",
    "economic_buyer": "Get introduced to the budget owner; ask who signed the last purchase of this size.",
    "decision_criteria": "Write down the must-haves and get the customer to confirm them by email.",
    "decision_process": "Map the steps from technical win to signature, with owners and dates.",
    "identify_pain": "Find the business event behind the interest; 'it's slow' is not a pain.",
    "champion": "Test for a champion: ask who will present this internally and what they gain.",
}

SYSTEM = (
    "You are a sales operations analyst. From the call transcript, extract MEDDIC. For each field return "
    '{"status": "confirmed"|"partial"|"missing", "summary": str, "evidence": str} where evidence is an exact quote '
    "of what the CUSTOMER said (empty if missing). Also return competitors (list of names), budget_allocated (bool) "
    "and timeline_risk (bool). Reply with one JSON object with keys " + ", ".join(FIELDS) +
    ", competitors, budget_allocated, timeline_risk."
)


@dataclass
class Field:
    name: str
    status: str
    summary: str
    evidence: str


@dataclass
class Assessment:
    call: Call
    fields: dict[str, Field]
    competitors: list[str]
    budget_allocated: bool
    timeline_risk: bool
    single_threaded: bool
    score: int = 0
    risks: list[str] = field(default_factory=list)
    stage_gaps: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


ROLE = r"(?:CFO|CEO|CTO|VP|director|lead|manager|engineer)"


def stakeholders(text: str) -> set[str]:
    """Named people the customer brings up: "Sam from facilities", "CFO, Mark Ellis", "Maria, our lead"."""
    pats = [r"\b([A-Z][a-z]+) from [a-z]", rf"{ROLE},? ([A-Z][a-z]+)", r"\b([A-Z][a-z]+), our "]
    return {m for p in pats for m in re.findall(p, text)}


def build_prompt(call: Call) -> str:
    lines = [f"DEAL: {call.deal}", f"STAGE: {call.stage}"]
    lines += [f"{'SELLER' if t.is_seller else 'CUSTOMER'} {t.speaker}: {t.text}" for t in call.turns]
    return "\n".join(lines)


def extract(llm: LLMClient, call: Call) -> Assessment:
    raw = llm.complete(SYSTEM, build_prompt(call))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError(f"no JSON object in model reply for {call.deal}")
    data = json.loads(m.group(0))
    fields = {}
    for name in FIELDS:
        d = data.get(name) or {}
        status = d.get("status", "missing")
        evidence = d.get("evidence", "")
        if status in ("confirmed", "partial") and not quote_in(call, evidence):
            status = "unverified"  # the model's claim has no support in what the customer actually said
        fields[name] = Field(name, status, d.get("summary", ""), evidence)
    people = call.customer_speakers
    # a name mentioned by the customer that isn't the speaker means more than one contact is engaged
    others = {m for t in call.turns if not t.is_seller for m in stakeholders(t.text)}
    a = Assessment(call, fields, list(data.get("competitors", [])), bool(data.get("budget_allocated", True)),
                   bool(data.get("timeline_risk", False)), single_threaded=len(people) + len(others - set(people)) < 2)
    score(a)
    return a


def score(a: Assessment) -> Assessment:
    """MEDDIC coverage (0-100) discounted by risk multipliers. Multiplicative so a deal with good coverage
    but no budget is clearly worse, while a thin deal isn't pushed to a meaningless zero."""
    base = sum(WEIGHTS[f] * CREDIT[a.fields[f].status] for f in FIELDS)
    penalties = []
    if a.competitors:
        penalties.append((min(0.2, 0.1 * len(a.competitors)), f"competing with {', '.join(a.competitors)}"))
    if not a.budget_allocated:
        penalties.append((0.2, "no budget allocated"))
    if a.single_threaded:
        penalties.append((0.15, "single-threaded: one customer contact"))
    if a.timeline_risk:
        penalties.append((0.05, "timeline risk raised on the call"))
    factor = 1.0
    for p, _ in penalties:
        factor *= 1 - p
    a.score = round(base * factor)
    a.risks = [r for _, r in penalties]
    a.stage_gaps = [f for f in STAGE_EXPECTS.get(a.call.stage, []) if a.fields[f].status != "confirmed"]
    order = a.stage_gaps + [f for f in FIELDS if a.fields[f].status != "confirmed" and f not in a.stage_gaps]
    a.actions = [NEXT_ACTION[f] for f in order[:3]]
    return a


def health(score: int) -> str:
    return "healthy" if score >= 75 else "watch" if score >= 50 else "at risk"
