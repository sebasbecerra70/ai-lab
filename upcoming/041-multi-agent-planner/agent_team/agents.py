"""Planner, executor and critic agents coordinated by an orchestrator over a shared scratchpad."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .llm import LLMClient, parse_json
from .scratchpad import Scratchpad
from .tools import ToolError, Toolbox

PLANNER_SYSTEM = """ROLE: planner
Break the task into steps. Reply with JSON only: {"steps": [{"id": snake_case_name, "tool": "calc"|"draft", "expr": arithmetic expression}]}.
calc expressions may use task inputs, fact names and earlier step ids, plus ceil/floor/min/max/round.
End with one "draft" step. If the scratchpad has a CRITIQUE, fix every issue it lists."""

CRITIC_SYSTEM = """ROLE: critic
Check whether the results fully answer the task, including physical and budget constraints in the facts.
Reply with JSON only: {"verdict": "approve"|"revise", "issues": [short strings]}."""

WRITER_SYSTEM = """ROLE: writer
Write a 2-3 sentence recommendation for an operations manager using only numbers in RESULTS."""


@dataclass
class Usage:
    calls: dict[str, int] = field(default_factory=dict)
    chars: int = 0

    def record(self, role: str, prompt: str, reply: str) -> None:
        self.calls[role] = self.calls.get(role, 0) + 1
        self.chars += len(prompt) + len(reply)

    @property
    def approx_tokens(self) -> int:
        return self.chars // 4


class Planner:
    def __init__(self, llm: LLMClient, usage: Usage):
        self.llm, self.usage = llm, usage

    def plan(self, task: str, inputs: dict, facts: dict, pad: Scratchpad) -> list[dict]:
        critique = pad.latest("critique")
        prompt = (f"TASK: {task}\nINPUTS: {json.dumps(inputs)}\nFACTS: {', '.join(sorted(facts))}\n"
                  + (f"CRITIQUE: {critique.content}\n" if critique else "")
                  + f"SCRATCHPAD:\n{pad.render({'plan', 'critique', 'error'})}")
        reply = self.llm.complete(PLANNER_SYSTEM, prompt)
        self.usage.record("planner", prompt, reply)
        steps = parse_json(reply)["steps"]
        ids = [s["id"] for s in steps]
        if len(set(ids)) != len(ids) or any(s["tool"] not in ("calc", "draft") for s in steps):
            raise ValueError("invalid plan: duplicate ids or unknown tool")
        return steps


class Executor:
    """Runs calc steps with the toolbox and delegates the draft step to the writer model."""

    def __init__(self, llm: LLMClient, tools: Toolbox, usage: Usage):
        self.llm, self.tools, self.usage = llm, tools, usage

    def run(self, steps: list[dict], inputs: dict, pad: Scratchpad, round_: int) -> dict[str, float]:
        results: dict[str, float] = {}
        draft = None
        for step in steps:
            if step["tool"] == "draft":
                prompt = f"TASK INPUTS: {json.dumps(inputs)}\nRESULTS: {json.dumps(results)}"
                draft = self.llm.complete(WRITER_SYSTEM, prompt)
                self.usage.record("writer", prompt, draft)
                pad.add(round_, "executor", "draft", draft)
                continue
            try:
                value = self.tools.calc(step["expr"], {**inputs, **results})
            except ToolError as e:
                pad.add(round_, "executor", "error", f"{step['id']}: {e}")
                continue
            results[step["id"]] = value
            pad.add(round_, "executor", "result", f"{step['id']} = {value:,.2f}".rstrip("0").rstrip("."))
        pad.variables = results
        return results


class Critic:
    def __init__(self, llm: LLMClient, usage: Usage):
        self.llm, self.usage = llm, usage

    def review(self, task: str, results: dict, pad: Scratchpad, round_: int) -> tuple[bool, list[str]]:
        # Deterministic guard first: tool errors are never approved, and cost no LLM call.
        errors = [e.content for e in pad.entries if e.round == round_ and e.kind == "error"]
        if errors:
            return False, [f"tool error: {e}" for e in errors]
        prompt = f"TASK: {task}\nRESULTS: {json.dumps(results)}\nDRAFT: {pad.latest('draft').content if pad.latest('draft') else ''}"
        reply = self.llm.complete(CRITIC_SYSTEM, prompt)
        self.usage.record("critic", prompt, reply)
        verdict = parse_json(reply)
        return verdict.get("verdict") == "approve", list(verdict.get("issues", []))


@dataclass
class Outcome:
    approved: bool
    rounds: int
    answer: str
    results: dict[str, float]
    pad: Scratchpad
    usage: Usage


def solve(task: str, inputs: dict, facts: dict, llm: LLMClient, max_rounds: int = 3) -> Outcome:
    pad, usage = Scratchpad(), Usage()
    planner, executor, critic = Planner(llm, usage), Executor(llm, Toolbox(facts), usage), Critic(llm, usage)
    results: dict[str, float] = {}
    for r in range(1, max_rounds + 1):
        steps = planner.plan(task, inputs, facts, pad)
        pad.add(r, "planner", "plan", " -> ".join(s["id"] for s in steps))
        results = executor.run(steps, inputs, pad, r)
        ok, issues = critic.review(task, results, pad, r)
        if ok:
            pad.add(r, "critic", "approval", "plan satisfies the task")
            return Outcome(True, r, pad.latest("draft").content, results, pad, usage)
        pad.add(r, "critic", "critique", "; ".join(issues))
    pad.add(max_rounds, "orchestrator", "note", "round budget exhausted; returning best effort for human review")
    draft = pad.latest("draft")
    return Outcome(False, max_rounds, draft.content if draft else "", results, pad, usage)
