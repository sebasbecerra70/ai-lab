"""Draft RFP answers from retrieved passages, enforce a confidence threshold, and verify citations."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .retrieval import BM25, Passage

SYSTEM = (
    "You draft answers to RFP questions for a logistics software vendor. Use ONLY the numbered passages from "
    "past approved proposals. Every sentence must end with a citation before the period, like this [1]. Do not add commitments, numbers "
    "or certifications that are not in the passages. Keep it under 80 words."
)


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class ExtractiveLLM:
    """Offline stand-in: returns the first two sentences of passage [1], each cited."""

    def complete(self, system: str, prompt: str) -> str:
        m = re.search(r"\[1\] \(.*?\)\nQ: .*?\nA: (.+?)(?:\n\[2\]|\n\nRFP question:)", prompt, re.DOTALL)
        if not m:
            return "No answer found in the passages."
        sentences = re.split(r"(?<=[.!?])\s+", m.group(1).strip())
        return " ".join(s.rstrip(".") + " [1]." for s in sentences[:2])


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 400, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")


@dataclass
class Draft:
    question: str
    status: str                      # "drafted" | "needs_sme"
    confidence: float
    answer: str = ""
    sources: list[Passage] = field(default_factory=list)
    citation_issues: list[str] = field(default_factory=list)


def check_citations(answer: str, n_sources: int) -> list[str]:
    issues = []
    for n in sorted({int(x) for x in re.findall(r"\[(\d+)\]", answer)}):
        if not 1 <= n <= n_sources:
            issues.append(f"cites [{n}] but only {n_sources} source(s) were provided")
    for s in re.split(r"(?<=[.!?])\s+", answer.strip()):
        if s and not re.search(r"\[\d+\][.!?]?$", s):
            issues.append(f"uncited sentence: {s[:60]}")
    return issues


def build_prompt(question: str, passages: list[Passage]) -> str:
    ctx = "\n".join(f"[{i}] ({p.source})\nQ: {p.question}\nA: {p.answer}" for i, p in enumerate(passages, 1))
    return f"{ctx}\n\nRFP question: {question}"


class RFPDrafter:
    def __init__(self, index: BM25, llm: LLMClient, k: int = 2, min_confidence: float = 0.4):
        self.index, self.llm, self.k, self.min_confidence = index, llm, k, min_confidence

    def draft(self, question: str) -> Draft:
        hits = self.index.search(question, self.k)
        confidence = hits[0][2] if hits else 0.0
        if confidence < self.min_confidence:
            # Below threshold the LLM is not called: a fluent guess in an RFP becomes a contractual promise.
            return Draft(question, "needs_sme", confidence, sources=[h[0] for h in hits])
        passages = [h[0] for h in hits]
        answer = self.llm.complete(SYSTEM, build_prompt(question, passages)).strip()
        return Draft(question, "drafted", confidence, answer, passages, check_citations(answer, len(passages)))
