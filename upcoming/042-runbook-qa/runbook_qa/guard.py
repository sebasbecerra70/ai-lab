"""Safety guard: refuse requests to skip or defeat a safety control, citing the rule that forbids it."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .retriever import Procedure

# Intent patterns that signal "help me get around a control". Kept explicit and reviewable on purpose:
# a missed refusal here can hurt someone, so this is not left to the model.
UNSAFE_INTENTS = [
    (r"\b(bypass|remove|cut|override|skip)\b.*\b(lock|lockout|tag)\b", "defeating lockout/tagout"),
    (r"\b(someone|somebody|another|other person|colleague)\b.*\block\b", "defeating lockout/tagout"),
    (r"\breset\b.*\b(again|twice|second time|keeps? tripping|multiple)\b", "repeatedly resetting a tripped breaker"),
    (r"\bopen\b.*\b(cabinet|battery)\b.*\bthermal runaway\b", "opening batteries in thermal runaway"),
    (r"\b(without|skip|no)\b.*\b(approval|electrician|qualified|engineer)\b", "skipping a required approval"),
    (r"\b(disable|silence|ignore)\b.*\b(alarm|leak detection|fire)\b", "disabling a safety alarm"),
]
PROHIBITION = re.compile(r"\b(do not|never|only)\b", re.I)


@dataclass
class Refusal:
    reason: str
    rule: str | None      # verbatim prohibition from the runbook, if one was found
    citation: str | None


def check(question: str, candidates: list[Procedure]) -> Refusal | None:
    q = question.lower()
    for pattern, reason in UNSAFE_INTENTS:
        if re.search(pattern, q):
            rule, cite = _find_rule(question, candidates)
            return Refusal(reason, rule, cite)
    return None


def _find_rule(question: str, candidates: list[Procedure]) -> tuple[str | None, str | None]:
    """Pick the prohibition step with the most word overlap with the question."""
    qwords = set(re.findall(r"[a-z]+", question.lower()))
    best, best_overlap = (None, None), 0
    for p in candidates:
        for n, step in enumerate(p.steps, 1):
            if PROHIBITION.search(step):
                overlap = len(qwords & set(re.findall(r"[a-z]+", step.lower())))
                if overlap > best_overlap:
                    best, best_overlap = (step, p.step_id(n)), overlap
    return best
