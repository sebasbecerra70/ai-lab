"""Pairwise judging with order swapping, and rubric judging with strict output parsing."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import LLMClient

PAIRWISE_SYSTEM = (
    "You are an impartial evaluator of customer-support answers. Compare two responses to the same question. "
    "Judge accuracy against the reference first, then helpfulness, then concision. Ignore response order and length "
    'for its own sake. Reply with JSON only: {"reasoning": "<one sentence>", "winner": "1" | "2" | "tie"}.'
)

RUBRIC = {
    "correctness": "Facts agree with the reference; no invented policies, prices or timelines.",
    "completeness": "Answers every part of the question and gives the next step.",
    "concision": "No filler; a customer can act on it in one read.",
    "tone": "Polite and plain; no blame, no condescension.",
}

RUBRIC_SYSTEM = (
    "You grade one customer-support answer against a rubric. Score each criterion 1-5 (5 best). "
    'Reply with JSON only: {"scores": {"correctness": n, "completeness": n, "concision": n, "tone": n}, "reasoning": "<one sentence>"}.'
)


class JudgeOutputError(ValueError):
    pass


def parse_json(text: str) -> dict:
    """Accept bare JSON or JSON inside a code fence; reject anything else."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise JudgeOutputError(f"no JSON object in judge output: {text[:80]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise JudgeOutputError(str(e)) from e


def pairwise_prompt(question: str, first: str, second: str, reference: str) -> str:
    return (f"<question>\n{question}\n</question>\n<reference>\n{reference}\n</reference>\n"
            f"<response_1>\n{first}\n</response_1>\n<response_2>\n{second}\n</response_2>")


@dataclass(frozen=True)
class PairVerdict:
    winner: str  # "A", "B" or "tie"
    forward: str  # raw verdict with A shown first
    backward: str  # raw verdict with B shown first
    consistent: bool


def _ask_pair(llm: LLMClient, prompt: str) -> str:
    out = parse_json(llm.complete(PAIRWISE_SYSTEM, prompt)).get("winner")
    if out not in ("1", "2", "tie"):
        raise JudgeOutputError(f"bad winner {out!r}")
    return out


def judge_pair(llm: LLMClient, question: str, a: str, b: str, reference: str = "") -> PairVerdict:
    """Ask twice with the order swapped. Only a verdict that survives the swap counts; otherwise it's a tie."""
    fwd = _ask_pair(llm, pairwise_prompt(question, a, b, reference))
    bwd = _ask_pair(llm, pairwise_prompt(question, b, a, reference))
    fwd_label = {"1": "A", "2": "B", "tie": "tie"}[fwd]
    bwd_label = {"1": "B", "2": "A", "tie": "tie"}[bwd]
    consistent = fwd_label == bwd_label
    return PairVerdict(fwd_label if consistent else "tie", fwd_label, bwd_label, consistent)


@dataclass(frozen=True)
class RubricScore:
    scores: dict[str, int]

    @property
    def overall(self) -> float:
        return sum(self.scores.values()) / len(self.scores)


def judge_rubric(llm: LLMClient, question: str, answer: str, reference: str = "", retries: int = 1) -> RubricScore:
    rubric = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
    prompt = (f"<rubric>\n{rubric}\n</rubric>\n<question>\n{question}\n</question>\n"
              f"<reference>\n{reference}\n</reference>\n<response>\n{answer}\n</response>")
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            scores = parse_json(llm.complete(RUBRIC_SYSTEM, prompt))["scores"]
            if set(scores) != set(RUBRIC) or not all(isinstance(v, int) and 1 <= v <= 5 for v in scores.values()):
                raise JudgeOutputError(f"scores must be ints 1-5 for {sorted(RUBRIC)}: {scores}")
            return RubricScore(scores)
        except (JudgeOutputError, KeyError, TypeError) as e:
            last = e
    raise JudgeOutputError(f"judge failed after {retries + 1} attempts: {last}")
