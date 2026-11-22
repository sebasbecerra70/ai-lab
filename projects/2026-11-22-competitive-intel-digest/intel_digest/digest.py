"""Ask the LLM for a cited digest of the ranked changes, then verify the citations."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .diff import Change
from .llm import LLMClient

SYSTEM = (
    "You are a competitive intelligence analyst writing for a BD and product leadership audience. "
    "Summarize the competitor changes below, grouped by competitor, as short bullets. Cite every claim with the "
    "change id in brackets, e.g. [C3]. Skip low-severity noise. For each competitor end with one 'So what:' line "
    "explaining the implication for us, given our differentiators and prices. Do not speculate beyond the changes."
)


@dataclass
class Audit:
    unknown: list[str] = field(default_factory=list)       # cited ids that do not exist
    uncited_high: list[str] = field(default_factory=list)  # high-severity changes the digest skipped

    @property
    def ok(self) -> bool:
        return not self.unknown and not self.uncited_high


def build_prompt(changes: list[Change], us: dict) -> str:
    lines = [f"WE ARE: {us['name']} ({us['category']})",
             f"OUR DIFFERENTIATORS: {', '.join(us['differentiators'])}",
             f"OUR PRICES: {', '.join(f'{k} ${v}' for k, v in us['reference_prices'].items())}",
             "CHANGES (id | competitor | severity | kind | detail):"]
    lines += [f"[{c.id}] {c.competitor} | {c.severity} | {c.kind} | {c.detail}" for c in changes]
    return "\n".join(lines)


def audit(text: str, changes: list[Change]) -> Audit:
    ids = {c.id for c in changes}
    cited = set(re.findall(r"\[(C\d+)\]", text))
    return Audit(sorted(cited - ids, key=lambda x: int(x[1:])),
                 [c.id for c in changes if c.severity == "high" and c.id not in cited])


def write_digest(llm: LLMClient, changes: list[Change], us: dict) -> tuple[str, Audit]:
    text = llm.complete(SYSTEM, build_prompt(changes, us))
    return text, audit(text, changes)
