"""LLM client interface: a deterministic heuristic judge for tests/offline, and a real Claude client."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

WORD = re.compile(r"[a-z0-9']+")
STOP = set("a an the and or of to in on for is are be it this that with you your we our i can will as at by from".split())


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


def _terms(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 2}


def heuristic_quality(question: str, answer: str, reference: str = "") -> float:
    """Crude quality proxy: overlap with the question and reference, minus a penalty for rambling."""
    target = _terms(question) | _terms(reference)
    hit = len(_terms(answer) & target) / max(1, len(target))
    words = len(answer.split())
    ramble = max(0, words - 80) / 200
    hedge = 0.15 if re.search(r"\b(i think|maybe|not sure|probably)\b", answer.lower()) else 0.0
    return round(hit - ramble - hedge, 4)


class MockJudge:
    """Offline judge with a deliberate weakness: when two answers are close, it prefers whichever it saw first.

    That mimics the position bias real LLM judges show and lets the swap test catch it deterministically.
    """

    def __init__(self, position_bias: float = 0.15):
        self.position_bias = position_bias

    def complete(self, system: str, prompt: str) -> str:
        sections = dict(re.findall(r"<(\w+)>\n?(.*?)\n?</\1>", prompt, re.S))
        q, ref = sections.get("question", ""), sections.get("reference", "")
        if "response_1" in sections:
            s1 = heuristic_quality(q, sections["response_1"], ref)
            s2 = heuristic_quality(q, sections["response_2"], ref)
            if abs(s1 - s2) <= self.position_bias:
                winner = "1"
            else:
                winner = "1" if s1 > s2 else "2"
            return json.dumps({"reasoning": f"scores {s1:.2f} vs {s2:.2f}", "winner": winner})
        ans = sections.get("response", "")
        base = heuristic_quality(q, ans, ref)
        words = len(ans.split())
        correctness = 1 + round(4 * min(1.0, max(0.0, base * 1.6)))
        concise = 5 if words <= 60 else 4 if words <= 100 else 2
        tone = 2 if re.search(r"\b(obviously|just|simply)\b", ans.lower()) else 4
        return json.dumps({"scores": {"correctness": correctness, "completeness": max(1, correctness - (1 if words < 15 else 0)),
                                      "concision": concise, "tone": tone}, "reasoning": "heuristic"})


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 600, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
