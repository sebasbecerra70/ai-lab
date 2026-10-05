"""LLM client interface: a deterministic mock for tests, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Restates the first retrieved procedure as numbered steps with citations.

    `hallucinate=True` makes it cite a step that was never in the context, which
    exercises the citation validator the same way a misbehaving model would.
    """

    def __init__(self, hallucinate: bool = False):
        self.hallucinate = hallucinate

    def complete(self, system: str, prompt: str) -> str:
        steps = re.findall(r"^\[([^\]]+#[^\]]+:\d+)\] (.+)$", prompt, re.M)
        if not steps:
            return "NOT_COVERED"
        proc = steps[0][0].rsplit(":", 1)[0]
        lines = [f"{i}. {text} [{sid}]" for i, (sid, text) in enumerate((s for s in steps if s[0].startswith(proc + ":")), 1)]
        if self.hallucinate:
            lines.append(f"{len(lines) + 1}. Power-cycle the whole row to clear the fault. [{proc}:99]")
        return "\n".join(lines)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 800,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
