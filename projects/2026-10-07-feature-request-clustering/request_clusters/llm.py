"""LLM client interface: deterministic mock for tests/demo, real Claude client when ANTHROPIC_API_KEY is set."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Builds a label from the 'Top terms:' line of the prompt, so output is stable and offline."""

    def complete(self, system: str, prompt: str) -> str:
        m = re.search(r"Top terms: (.+)", prompt)
        terms = [t.strip() for t in m.group(1).split(",")][:3] if m else ["misc"]
        return f"{' / '.join(t.upper() if len(t) <= 4 else t.capitalize() for t in terms)} requests"


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 64, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
