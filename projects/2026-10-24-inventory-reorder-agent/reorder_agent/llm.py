"""LLM client interface: a template memo writer for tests/offline, and a real Claude client."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    def complete(self, system: str, prompt: str) -> str:
        from .agent import template_memo  # local import: agent imports this module

        return template_memo(json.loads(prompt[prompt.index("{"):]))


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 300, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
