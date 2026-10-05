"""The agent loop: ask the model, run any tool calls, feed results back, stop on an answer or the step cap."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .llm import ChatLLM
from .tools import ToolRegistry

SYSTEM = (
    "You are a data center operations assistant. Use the tools for every number: look up site "
    "metrics with `lookup`, do arithmetic with `calculator`, and convert units with `convert_units`. "
    "Never guess a metric. Answer in one or two sentences with units."
)


@dataclass
class Step:
    tool: str
    args: dict
    result: str
    is_error: bool


@dataclass
class RunResult:
    answer: str
    steps: list[Step] = field(default_factory=list)
    stopped_by_guard: bool = False


class Agent:
    def __init__(self, llm: ChatLLM, registry: ToolRegistry, max_steps: int = 6):
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.llm, self.registry, self.max_steps = llm, registry, max_steps

    def run(self, question: str) -> RunResult:
        messages: list[dict] = [{"role": "user", "content": question}]
        steps: list[Step] = []
        for _ in range(self.max_steps):
            turn = self.llm.chat(SYSTEM, messages, self.registry.specs())
            calls = [b for b in turn["content"] if b["type"] == "tool_use"]
            text = "".join(b.get("text", "") for b in turn["content"] if b["type"] == "text").strip()
            if not calls:
                return RunResult(text, steps)
            messages.append({"role": "assistant", "content": turn["content"]})
            results = []
            for call in calls:
                content, is_error = self.registry.dispatch(call["name"], call.get("input", {}))
                steps.append(Step(call["name"], call.get("input", {}), content, is_error))
                block = {"type": "tool_result", "tool_use_id": call["id"], "content": content}
                if is_error:
                    block["is_error"] = True
                results.append(block)
            messages.append({"role": "user", "content": results})
        # The guard: a confused model can loop on tools forever and burn tokens.
        return RunResult(f"Stopped after {self.max_steps} steps without a final answer.", steps, True)


def format_trace(result: RunResult) -> str:
    lines = []
    for i, s in enumerate(result.steps, 1):
        flag = " ERROR" if s.is_error else ""
        lines.append(f"  step {i}: {s.tool}({json.dumps(s.args)}) -> {s.result}{flag}")
    lines.append(f"  answer: {result.answer}")
    return "\n".join(lines)
