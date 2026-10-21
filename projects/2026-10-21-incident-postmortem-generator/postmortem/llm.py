"""LLM client interface: a deterministic template writer for tests/offline, and a real Claude client."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class MockLLM:
    """Writes the postmortem from the FACTS JSON in the prompt. Same input, same draft."""

    def complete(self, system: str, prompt: str) -> str:
        f = json.loads(prompt[prompt.index("FACTS:") + 6:].strip())
        d = f["durations"]
        lines = [
            f"# Postmortem: {f['title']}",
            "",
            "## Summary",
            f"At {f['start']} a fault began ({f['first_fault']}). Customers saw errors until mitigation at {f['mitigated']}; "
            f"the incident was resolved at {f['resolved']}.",
            "",
            "## Impact",
            f"- {f['impact']}",
            f"- Detect {d.get('time_to_detect', 'n/a')}, acknowledge {d.get('time_to_acknowledge', 'n/a')}, "
            f"mitigate {d.get('time_to_mitigate', 'n/a')}, resolve {d.get('time_to_resolve', 'n/a')}.",
            "",
            "## Timeline",
            *[f"- {e}" for e in f["key_events"]],
            "",
            "## Root cause and contributing factors",
        ]
        if f["suspected_change"]:
            lines.append(f"- Trigger (suspected): {f['suspected_change']}, shortly before the first fault.")
        lines += [f"- {x}" for x in f["findings"]]
        lines += ["", "## What went well", *[f"- {x}" for x in f["went_well"]], "",
                  "## What was hard", *[f"- {x}" for x in f["went_poorly"]], "",
                  "## Action items", *[f"- [{a['priority']}] {a['action']} (owner: {a['owner']})" for a in f["action_items"]]]
        return "\n".join(lines)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": 1500, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
