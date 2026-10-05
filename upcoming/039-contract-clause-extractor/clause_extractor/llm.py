"""LLM client interface: deterministic mock for tests, real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Stands in for a well-behaved model: classifies by heading and answers in the JSON contract.

    `fail_on` lets tests simulate malformed output for specific clause numbers.
    """

    HEADING_TYPES = [("renew", "renewal"), ("term and", "renewal"), ("terminat", "termination"), ("term", "renewal"),
                     ("liabil", "liability"), ("indemn", "indemnification"), ("fee", "payment"),
                     ("payment", "payment"), ("confiden", "confidentiality"), ("governing", "governing_law")]

    def __init__(self, fail_on: set[int] | None = None):
        self.fail_on = fail_on or set()

    def complete(self, system: str, prompt: str) -> str:
        num = int(re.search(r"CLAUSE (\d+)", prompt).group(1))
        if num in self.fail_on:
            return "Sure! This clause looks like a renewal clause."  # not JSON
        heading = re.search(r"HEADING: (.*)", prompt).group(1).lower()
        ctype = next((t for k, t in self.HEADING_TYPES if k in heading), "other")
        return json.dumps({"type": ctype, "confidence": 0.9 if ctype != "other" else 0.7})


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model, "max_tokens": 300, "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
