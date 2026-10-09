"""LLM client interface: replayed recordings for tests/demo, and a real Claude client."""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class RecordedLLM:
    """Replays recorded model outputs keyed by a string found in the prompt (e.g. the invoice number).

    The recordings include the failure modes seen in production: code fences, chatty preambles,
    a non-ISO date, a transposed total and a truncated response.
    """

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls = 0

    @classmethod
    def from_file(cls, path: str | Path) -> "RecordedLLM":
        return cls(json.loads(Path(path).read_text()))

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        for key, response in self.responses.items():
            if key in prompt:
                return response
        return "{}"


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 1500, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
