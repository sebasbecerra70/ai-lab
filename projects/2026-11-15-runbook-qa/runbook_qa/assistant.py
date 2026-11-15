"""Answer a runbook question: guard -> retrieve -> generate -> validate citations -> fall back if needed."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import guard
from .llm import LLMClient
from .retriever import BM25, Procedure

SYSTEM = (
    "You are a data center operations assistant. Answer ONLY from the runbook steps provided. "
    "Reply with numbered steps; end every step with the [id] of the runbook step it comes from. "
    "Keep warnings and 'do not' steps. If the steps do not answer the question, reply exactly NOT_COVERED."
)
CITE = re.compile(r"\[([^\]]+#[^\]]+:\d+)\]")
MIN_SCORE = 2.0  # below this BM25 score the best match is a coincidence, not an answer
MIN_TERMS = 2    # one shared word ("portal") is not enough to claim a runbook covers the question


@dataclass
class Answer:
    status: str                    # answered | refused | not_covered
    text: str
    citations: list[str] = field(default_factory=list)
    source: str = "llm"            # llm | extractive (validator rejected the model's answer)
    problems: list[str] = field(default_factory=list)


def build_prompt(question: str, procs: list[Procedure]) -> str:
    blocks = []
    for p in procs:
        blocks.append(f"## {p.title} ({p.doc})")
        blocks.extend(f"[{p.step_id(n)}] {s}" for n, s in enumerate(p.steps, 1))
    return "RUNBOOK STEPS:\n" + "\n".join(blocks) + f"\n\nQUESTION: {question}"


def validate(text: str, allowed: set[str]) -> list[str]:
    """Every step line must cite, and every citation must exist in the retrieved context."""
    problems = []
    lines = [ln for ln in text.splitlines() if re.match(r"^\s*\d+\.", ln)]
    if not lines:
        problems.append("no numbered steps")
    for ln in lines:
        cites = CITE.findall(ln)
        if not cites:
            problems.append(f"uncited step: {ln.strip()[:60]}")
        problems.extend(f"unknown citation [{c}]" for c in cites if c not in allowed)
    return problems


def extractive(proc: Procedure) -> str:
    return "\n".join(f"{n}. {s} [{proc.step_id(n)}]" for n, s in enumerate(proc.steps, 1))


class RunbookQA:
    def __init__(self, procs: list[Procedure], llm: LLMClient, k: int = 2):
        self.index, self.llm, self.k = BM25(procs), llm, k

    def ask(self, question: str) -> Answer:
        hits = self.index.search(question, self.k, MIN_TERMS)
        refusal = guard.check(question, [p for p, _ in self.index.search(question, 4)])
        if refusal:
            text = f"I can't help with {refusal.reason}."
            if refusal.rule:
                text += f' The runbook says: "{refusal.rule}" [{refusal.citation}]'
            return Answer("refused", text, [refusal.citation] if refusal.citation else [], source="guard")
        if not hits or hits[0][1] < MIN_SCORE:
            return Answer("not_covered", "No runbook covers this. Escalate to the shift lead.", source="retriever")

        procs = [p for p, _ in hits]
        allowed = {p.step_id(n) for p in procs for n in range(1, len(p.steps) + 1)}
        raw = self.llm.complete(SYSTEM, build_prompt(question, procs)).strip()
        if raw == "NOT_COVERED":
            return Answer("not_covered", "No runbook covers this. Escalate to the shift lead.")
        problems = validate(raw, allowed)
        if problems:
            text, source = extractive(procs[0]), "extractive"
        else:
            text, source = raw, "llm"
        return Answer("answered", text, sorted(set(CITE.findall(text)), key=text.find), source, problems)
