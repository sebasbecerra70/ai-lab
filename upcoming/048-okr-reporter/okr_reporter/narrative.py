"""Turn scored OKRs into a facts block, ask the LLM for a status update, and check it against the facts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm import LLMClient
from .scoring import Objective, biggest_gap, fmt

SYSTEM = (
    "You write the weekly OKR status update for a product leadership team. Use ONLY the facts given; never "
    "introduce a number that is not in the facts. Lead with the overall picture, then what is going well, then "
    "every KR that is off track or at risk with its forecast, then one concrete ask. Under 200 words, markdown."
)


def facts(objectives: list[Objective], week: int, total: int) -> str:
    lines = [f"WEEK {week} of {total}"]
    for o in objectives:
        lines.append(f"{o.id} {o.title}: score {o.score:.0%}, projected {o.projected:.0%}")
        for k in o.krs:
            lines.append(f"{k.id} | {k.title} | now {fmt(k, k.current)} | target {fmt(k, k.target)} | "
                         f"progress {k.progress * 100:.0f}% vs {k.expected * 100:.0f}% expected | "
                         f"quarter-end forecast {fmt(k, k.forecast)} | {k.status}")
    krs = [k for o in objectives for k in o.krs]
    n_bad = sum(k.status in ("off track", "at risk") for k in krs)
    lines.append(f"OVERALL: {len(krs) - n_bad} of {len(krs)} KRs on track or done, {n_bad} need attention")
    gap = biggest_gap(objectives)
    if gap:
        lines.append(f"BIGGEST GAP: {gap.id}")
    return "\n".join(lines)


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


@dataclass
class Check:
    unknown_numbers: list[str] = field(default_factory=list)
    missing_krs: list[str] = field(default_factory=list)  # off-track/at-risk KRs the narrative skipped

    @property
    def ok(self) -> bool:
        return not self.unknown_numbers and not self.missing_krs


def check(narrative: str, facts_text: str, objectives: list[Objective]) -> Check:
    known = set(NUMBER.findall(facts_text))
    # KR ids like "KR1.1" are labels, not claims
    claims = NUMBER.findall(re.sub(r"\b[OK]R?\d+(?:\.\d+)?\b", "", narrative))
    unknown = sorted({n for n in claims if n not in known})
    flagged = [k.id for o in objectives for k in o.krs if k.status in ("off track", "at risk")]
    return Check(unknown, [kr for kr in flagged if kr not in narrative])


def write_update(llm: LLMClient, objectives: list[Objective], week: int, total: int) -> tuple[str, Check]:
    f = facts(objectives, week, total)
    text = llm.complete(SYSTEM, "FACTS:\n" + f)
    return text, check(text, f, objectives)
