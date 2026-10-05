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
    """Writes the update from the FACTS lines, the way a careful PM would."""

    def complete(self, system: str, prompt: str) -> str:
        facts = re.findall(r"^(KR[\d.]+) \| (.+?) \| now (.+?) \| target (.+?) \| progress (\d+)% vs (\d+)% expected"
                           r" \| quarter-end forecast (.+?) \| (.+)$", prompt, re.M)
        overall = re.search(r"^OVERALL: (.+)$", prompt, re.M).group(1)
        good = [f for f in facts if f[7] in ("on track", "done")]
        bad = sorted((f for f in facts if f[7] in ("off track", "at risk")), key=lambda f: f[7] != "off track")
        lines = [f"**Headline:** {overall}.", "", "**Going well**"]
        lines += [f"- {kr} {title}: {now} against a {target} target, {prog}% of the way there ({status})."
                  for kr, title, now, target, prog, _, _, status in good] or ["- Nothing is on track yet."]
        lines += ["", "**Needs attention**"]
        lines += [f"- {kr} {title} is {status}: {prog}% done vs {exp}% expected; the current trend lands at "
                  f"{fc} against {target}." for kr, title, _, target, prog, exp, fc, status in bad] or ["- None."]
        gap = re.search(r"^BIGGEST GAP: (\S+)$", prompt, re.M)
        if gap:
            lines += ["", f"**Ask:** agree on a recovery plan or a re-scoped target for {gap.group(1)} by next review."]
        return "\n".join(lines)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 900,
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
