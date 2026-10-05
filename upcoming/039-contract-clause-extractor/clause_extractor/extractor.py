"""Hybrid pipeline: the LLM classifies each clause, rules validate and extract fields, rules cover failures."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .llm import LLMClient
from .risk import Policy, RiskFlag, assess, risk_score
from .rules import CLAUSE_TYPES, Clause, classify, extract_fields, our_role, split_clauses

SYSTEM = (
    "You classify commercial contract clauses. Reply with JSON only: "
    '{"type": one of ' + ", ".join(CLAUSE_TYPES) + ', "confidence": number between 0 and 1}. '
    "Use the clause body, not just the heading."
)


def build_prompt(c: Clause) -> str:
    return f"CLAUSE {c.number}\nHEADING: {c.heading}\nTEXT: {c.text}"


def parse_llm(raw: str) -> dict | None:
    """Accept a JSON object (optionally inside a code fence); reject anything off-contract."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if data.get("type") not in CLAUSE_TYPES:
        return None
    conf = data.get("confidence", 0)
    if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        return None
    return data


@dataclass
class ContractReport:
    name: str
    role: str
    clauses: list[Clause]
    flags: list[RiskFlag]
    disagreements: list[int] = field(default_factory=list)  # clause numbers where LLM and rules differ
    fallbacks: list[int] = field(default_factory=list)

    @property
    def score(self) -> int:
        return risk_score(self.flags)


def analyze(name: str, text: str, llm: LLMClient | None, policy: Policy = Policy(),
            min_confidence: float = 0.6) -> ContractReport:
    role = our_role(text)
    clauses = split_clauses(text)
    disagreements, fallbacks = [], []
    for c in clauses:
        rule_type = classify(c)
        parsed = parse_llm(llm.complete(SYSTEM, build_prompt(c))) if llm else None
        if parsed and parsed.get("confidence", 0) >= min_confidence:
            c.type, c.source = parsed["type"], "llm"
            if parsed["type"] != rule_type:
                disagreements.append(c.number)
        else:
            c.type, c.source = rule_type, "rules"
            if llm:
                fallbacks.append(c.number)
        c.fields = extract_fields(c.type, c.text, role)
    return ContractReport(name, role, clauses, assess(clauses, role, policy), disagreements, fallbacks)


def analyze_dir(path: Path, llm: LLMClient | None) -> list[ContractReport]:
    return [analyze(p.stem, p.read_text(), llm) for p in sorted(Path(path).glob("*.txt"))]
