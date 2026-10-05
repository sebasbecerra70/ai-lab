"""LLM client interface: a deterministic mock for tests, and a real Claude client."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Echoes the first context passage so tests and demos run offline."""

    def complete(self, system: str, prompt: str) -> str:
        marker = "[1] "
        start = prompt.find(marker)
        if start == -1:
            return "I don't know based on the provided SOPs."
        passage = prompt[start + len(marker):].split("\n[2] ")[0].strip()
        first_line = next((ln for ln in passage.splitlines() if ln and not ln.startswith(("#", "source:"))), passage)
        return f"{first_line} [1]"


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 512,
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
