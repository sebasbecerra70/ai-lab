"""LLM client interface: a template mock for offline runs and tests, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Writes the memo from the FACTS block like a careful analyst would. `sloppy` names deal ids for which it
    misquotes the margin, the way a real model sometimes rounds or recalls a number wrong."""

    def __init__(self, sloppy: set[str] | None = None):
        self.sloppy = sloppy or set()

    def complete(self, system: str, prompt: str) -> str:
        f = json.loads(re.search(r"FACTS:\n(\{.*\})", prompt, re.S).group(1))
        margin = f["margin_pct"] + (12 if f["id"] in self.sloppy else 0)
        lines = [
            f"{f['customer']} ({f['id']}) requests {f['discount_pct']}% off ${f['list_arr']:,} list ARR, "
            f"for ${f['net_arr']:,} net ARR over {f['term_years']} year(s). Gross margin is {margin}%.",
        ]
        if f["allowances"]:
            lines.append(f"Policy credits {', '.join(f'{k} ({v} pts)' for k, v in f['allowances'].items())}, "
                         f"so it is assessed as {f['effective_discount_pct']}%.")
        lines.append(f"Recommendation: {f['status']}; approval required from {', '.join(f['approvers'])}.")
        for r in f["findings"]:
            lines.append(f"- {r}")
        if f.get("win_at_request_pct") is not None:
            lines.append(f"Win model: {f['win_at_request_pct']}% at the requested discount vs "
                         f"{f['win_at_counter_pct']}% at {f['counter_discount_pct']}%.")
        if f["give_gets"]:
            lines.append("Give-gets: " + "; ".join(f["give_gets"]) + ".")
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
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
