"""Facts for the narrative, the faithfulness check, and a draft-check-repair loop around the LLM."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .bridge import Bridge
from .kpis import Variance, fmt
from .llm import LLMClient

SYSTEM = (
    "You write the monthly operations summary for the executive team. Use only numbers from FACTS, copied "
    "exactly as formatted. Lead with the headline, then what is off plan and why, then the revenue bridge, then "
    "asks with owners. Mention every red KPI. 'Above/below plan' means the raw value; 'beat/missed' means "
    "better/worse given the metric's direction. Under 200 words, plain text."
)

UP_WORDS = r"\babove plan\b|\bover plan\b"
DOWN_WORDS = r"\bbelow plan\b|\bunder plan\b"
GOOD_WORDS = r"\bbeat\b|\bahead of plan\b|\bbetter than plan\b|\boutperform"
BAD_WORDS = r"\bmissed\b|\bbehind plan\b|\bworse than plan\b|\bshort of plan\b"
NUMBER = re.compile(r"(?<![\w.])\$?(\d[\d,]*(?:\.\d+)?)(?:\s?(M|k)\b|%|\s?pp\b)?")


def build_facts(variances: list[Variance], br: Bridge) -> dict:
    status = [v.status for v in variances]
    kpis = []
    for v in sorted(variances, key=lambda v: -v.severity):
        k = v.kpi
        kpis.append({
            "metric": k.metric, "status": v.status, "favorable": v.favorable, "owner": k.owner,
            "direction": "higher is better" if k.direction == "up" else "lower is better",
            "actual": fmt(k.actual, k.unit), "plan": fmt(k.plan, k.unit),
            "vs_plan": fmt(v.vs_plan, k.unit, signed=True), "vs_plan_pct": f"{v.vs_plan_pct:+.1f}%",
            "vs_prior": fmt(v.vs_prior, k.unit, signed=True),
        })
    segs = sorted(((name, sum(e.values())) for name, e in br.by_segment.items()), key=lambda x: x[1])
    return {
        "kpi_count": len(variances), "green": status.count("green"), "amber": status.count("amber"),
        "red": status.count("red"), "kpis": kpis,
        "revenue_bridge": {"plan": fmt(br.plan, "usd"), "volume": fmt(br.volume, "usd", True),
                           "mix": fmt(br.mix, "usd", True), "price": fmt(br.price, "usd", True),
                           "actual": fmt(br.actual, "usd"),
                           "by_segment": {n: fmt(x, "usd", True) for n, x in segs}},
    }


def numbers_in(text: str) -> list[tuple[str, float, float]]:
    """(token, value, half a unit of its last digit). '$4.23M' -> 4,230,000 give or take 5,000."""
    out = []
    for m in NUMBER.finditer(text):
        digits, suffix = m.group(1).replace(",", ""), m.group(2)
        scale = {"M": 1e6, "k": 1e3}.get(suffix or "", 1.0)
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        out.append((m.group(0).strip(), float(digits) * scale, 0.5 * 10 ** -decimals * scale))
    return out


def _fact_values(facts: dict) -> list[float]:
    vals = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.append(abs(float(x)))
        elif isinstance(x, str):
            vals.extend(v for _, v, _ in numbers_in(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(facts)
    return vals


def check(narrative: str, facts: dict) -> list[str]:
    """Number faithfulness: every number must be a correct rounding of a fact. Direction: a clause that names a
    KPI must not say above/below or beat/missed against the facts. Coverage: every red KPI is mentioned."""
    allowed = _fact_values(facts)
    issues = [f"number not in facts: {tok}" for tok, x, half in numbers_in(narrative)
              if not any(abs(x - v) <= half + 1e-9 for v in allowed)]
    by_name = {k["metric"].lower(): k for k in facts["kpis"]}
    for clause in re.split(r"[.;\n]| while | but | whereas ", narrative):
        low = clause.lower()
        for name, k in by_name.items():
            if name not in low:
                continue
            raised = not k["vs_plan"].startswith("-")
            if re.search(UP_WORDS, low) and not raised or re.search(DOWN_WORDS, low) and raised:
                issues.append(f"wrong direction for {k['metric']}: actual {k['actual']} vs plan {k['plan']}")
            if re.search(GOOD_WORDS, low) and not k["favorable"] or re.search(BAD_WORDS, low) and k["favorable"]:
                issues.append(f"wrong verdict for {k['metric']}: {'favorable' if k['favorable'] else 'unfavorable'}")
    for k in facts["kpis"]:
        if k["status"] == "red" and k["metric"].lower() not in narrative.lower():
            issues.append(f"red KPI not mentioned: {k['metric']}")
    return issues


def template(facts: dict) -> str:
    """Correct by construction, dull by design: the fallback when the model can't produce a clean draft."""
    lines = [f"{facts['green']} of {facts['kpi_count']} KPIs on plan, {facts['amber']} amber, {facts['red']} red."]
    for k in facts["kpis"]:
        if k["status"] != "green":
            lines.append(f"{k['metric']} ({k['status']}): {k['actual']} vs plan {k['plan']}, {k['vs_plan']}. "
                         f"Owner: {k['owner']}.")
    b = facts["revenue_bridge"]
    lines.append(f"Revenue bridge: plan {b['plan']}, volume {b['volume']}, mix {b['mix']}, price {b['price']}, "
                 f"actual {b['actual']}.")
    return "\n".join(lines)


@dataclass
class Narrative:
    text: str
    attempts: int
    issues_by_attempt: list[list[str]]
    source: str        # llm | template


def narrate(llm: LLMClient, facts: dict, max_attempts: int = 2) -> Narrative:
    """Draft, check, and on failure send the problems back for one repair. Fall back to the template."""
    prompt = "FACTS:\n" + json.dumps(facts, indent=1)
    history: list[list[str]] = []
    for attempt in range(1, max_attempts + 1):
        text = llm.complete(SYSTEM, prompt).strip()
        issues = check(text, facts)
        history.append(issues)
        if not issues:
            return Narrative(text, attempt, history, "llm")
        prompt = ("FACTS:\n" + json.dumps(facts, indent=1) + "\n\nYOUR DRAFT:\n" + text +
                  "\n\nThe draft has these problems. Fix them and rewrite:\n- " + "\n- ".join(issues))
    return Narrative(template(facts), max_attempts, history, "template")
