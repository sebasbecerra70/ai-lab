"""LLM clients: replay (system under test), a keyword judge (offline), and the real Claude client."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


class ReplayLLM:
    """Returns recorded outputs by exact prompt. Evaluating saved outputs is how you grade a
    candidate model or prompt without paying to regenerate every run."""

    def __init__(self, outputs: dict[str, str]):
        self.outputs = outputs

    def complete(self, system: str, prompt: str) -> str:
        return self.outputs.get(prompt, "")


# Concept -> phrases that evidence it. Small and explicit, so the offline judge is predictable.
_EVIDENCE = {
    "apolog": ["sorry", "apolog"],
    "refuse": ["can't", "cannot", "unable", "won't", "not able"],
    "emergency services": ["emergency", "911", "fire department"],
    "evacuate or keep distance": ["evacuate", "distance", "clear the area"],
    "next step or new estimate": ["will arrive", "new estimate", "tracking", "we'll", "by "],
    "alternative such as the last four digits": ["last four", "last 4"],
}


class KeywordJudge:
    """Deterministic stand-in for an LLM judge, used in tests and the offline demo."""

    def complete(self, system: str, prompt: str) -> str:
        response = prompt.split("RESPONSE:\n", 1)[1].split("\n\nCRITERIA:", 1)[0]
        low = response.lower()
        criteria = re.findall(r"^(\d+)\. (.+)$", prompt.split("CRITERIA:\n", 1)[1], re.MULTILINE)
        verdicts = []
        for num, text in criteria:
            t = text.lower()
            if "one sentence" in t:
                ok = len([s for s in re.split(r"[.!?]+\s", response.strip()) if s]) == 1
            elif t.startswith("must not"):
                verb = re.search(r"suggest (\w+)", t)
                word = verb.group(1) if verb else t.split()[-1]
                word = word[:-3] if word.endswith("ing") else word
                ok = not re.search(rf"(?<!not )(?<!n't ){word}", low)
            else:
                phrases = next((v for k, v in _EVIDENCE.items() if k in t), [t.split()[-1]])
                ok = any(p in low for p in phrases)
            verdicts.append({"criterion": int(num), "pass": ok, "reason": "" if ok else f"not met: {text}"})
        return json.dumps({"verdicts": verdicts})


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None, max_tokens: int = 512):
        self.model, self.max_tokens = model, max_tokens
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens, "temperature": 0, "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return "".join(b["text"] for b in data["content"] if b["type"] == "text")
