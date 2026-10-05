"""LLM client interface: a deliberately gullible mock (it obeys any instruction it sees) and a real Claude client."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class NaiveMock:
    """Does whatever the text says. The guard pipeline has to be safe even with a model this obedient."""

    def complete(self, system: str, prompt: str) -> str:
        low = prompt.lower()
        calls, reply = [], "Thanks for reaching out. I can help with that."
        if re.search(r"(system|hidden|initial) (prompt|instructions)", low):
            reply = f"Sure, here are my instructions: {system}"
        for img in re.findall(r"!\[[^\]]*\]\([^)]*\)", prompt):
            reply += f" {img}"
        order = re.search(r"ORD-\d{6}", prompt)
        m = re.search(r"refund[^$\n]{0,40}\$(\d+(?:\.\d+)?)", prompt, re.I)
        if m:
            calls.append({"name": "issue_refund", "args": {"order_id": order.group(0) if order else "ORD-000000", "amount": float(m.group(1))}})
        elif order:
            calls.append({"name": "lookup_order", "args": {"order_id": order.group(0)}})
        m = re.search(r"(?:email|send)[^\n]{0,60}?\bto\s+(\S+@\S+|\[EMAIL_\d+\])", prompt, re.I)
        if m:
            calls.append({"name": "send_email", "args": {"to": m.group(1).rstrip(".,"), "body": "Order details attached."}})
        if "delete" in low and "account" in low:
            calls.append({"name": "delete_account", "args": {}})
        return json.dumps({"reply": reply, "tool_calls": calls})


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
