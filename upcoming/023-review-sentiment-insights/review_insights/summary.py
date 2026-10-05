"""LLM-written pain-point brief from the ranked aspects, with a check that every quote is verbatim."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol

from .aspects import AspectStats, Review

SYSTEM = (
    "You are a product analyst. Write a short brief for the product team on the top customer pain points. For each pain "
    "point: one line on what customers report, the numbers given (mentions, negative share), and one verbatim quote in double "
    "quotes with its review id. Quote exactly; do not paraphrase inside quotes. End with one recommended next step per pain point."
)


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    def complete(self, system: str, prompt: str) -> str:
        facts = json.loads(prompt[prompt.index("["):])
        lines = ["Top customer pain points:"]
        for i, f in enumerate(facts, 1):
            q = f["quotes"][0]
            lines.append(f"{i}. {f['aspect']}: {f['negative']} of {f['mentions']} mentions are negative "
                         f"({f['negative_share']:.0%}). \"{q['text']}\" ({q['id']})")
        lines.append("Next steps: " + "; ".join(f"investigate {f['aspect']} first" if i == 0 else f"then {f['aspect']}"
                                                for i, f in enumerate(facts)) + ".")
        return "\n".join(lines)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 700, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")


def build_facts(pains: list[AspectStats], quotes_per: int = 3) -> list[dict]:
    return [{
        "aspect": p.aspect, "mentions": p.mentions, "negative": p.negative, "negative_share": round(p.negative_share, 2),
        "pain_index": round(p.pain, 2),
        # Most negative quotes first, de-duplicated (templated reviews repeat sentences).
        "quotes": [{"id": rid, "text": s} for _, rid, s in _unique(sorted(p.quotes))[:quotes_per]],
    } for p in pains]


def _unique(quotes: list[tuple[float, str, str]]) -> list[tuple[float, str, str]]:
    seen, out = set(), []
    for q in quotes:
        if q[2] not in seen:
            seen.add(q[2])
            out.append(q)
    return out


def summarize(llm: LLMClient, pains: list[AspectStats]) -> str:
    return llm.complete(SYSTEM, "Pain points as JSON, ranked:\n" + json.dumps(build_facts(pains), indent=1))


def unverified_quotes(summary: str, reviews: list[Review]) -> list[str]:
    """Quoted strings (8+ chars) that do not appear verbatim in any review."""
    corpus = "\n".join(r.text for r in reviews)
    return [q for q in re.findall(r"\"([^\"]{8,})\"", summary) if q not in corpus]
