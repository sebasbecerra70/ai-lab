"""LLM client interface: a cue-phrase mock for offline runs, and a real Claude client via stdlib HTTP."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, prompt: str) -> str: ...


# Cue phrases per MEDDIC field: (confirmed cues, partial cues). Only customer turns are searched.
CUES = {
    "metrics": (r"\d[\d,.]* (thousand )?(dollars|percent)|\$\d", r"impact|slow|manual work"),
    "economic_buyer": (r"approves|i own the budget|i sign|signs off", r"finance|manager asked"),
    "decision_criteria": (r"must|is required|we need .+ and", r"needs to be|easy to use"),
    "decision_process": (r"validation|then .+ signs|sign by|redlines|procurement", r"next step"),
    "identify_pain": (r"caught short|emergency|lost two days|cooling failure|cost you", r"issues|slow"),
    "champion": (r"pushing this internally|internal champion|presented the pilot", r"my manager asked"),
}


class MockLLM:
    """Finds the first customer sentence matching each field's cues and returns it as verbatim evidence.
    `fabricate` makes it invent a quote for one field, the way a real model sometimes paraphrases."""

    def __init__(self, fabricate: dict[str, str] | None = None):
        self.fabricate = fabricate or {}

    def complete(self, system: str, prompt: str) -> str:
        deal = re.search(r"^DEAL: (.+)$", prompt, re.M).group(1)
        turns = re.findall(r"^CUSTOMER (\w+): (.+)$", prompt, re.M)
        sentences = [(who, s.strip()) for who, text in turns for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        out = {}
        for fld, (strong, weak) in CUES.items():
            if fld in self.fabricate and deal in self.fabricate[fld]:
                out[fld] = {"status": "confirmed", "summary": "invented", "evidence": self.fabricate[fld].split("|", 1)[1]}
                continue
            hit = next(((w, s) for w, s in sentences if re.search(strong, s, re.I)), None)
            status = "confirmed"
            if not hit:
                hit, status = next(((w, s) for w, s in sentences if re.search(weak, s, re.I)), None), "partial"
            if hit:
                out[fld] = {"status": status, "summary": f"{hit[0]}: {hit[1][:70]}", "evidence": hit[1]}
            else:
                out[fld] = {"status": "missing", "summary": "", "evidence": ""}
        competitors = sorted({c for _, s in sentences for c in ("Sunbird", "Nlyte", "Device42") if c in s})
        out["competitors"] = competitors
        out["budget_allocated"] = not any(re.search(r"\bno budget\b", s, re.I) for _, s in sentences)
        out["timeline_risk"] = any(re.search(r"might take|backed up|very busy|slip", s, re.I) for _, s in sentences)
        return json.dumps(out)


class AnthropicLLM:
    """Minimal Messages API client using only the standard library."""

    def __init__(self, model: str = "claude-sonnet-5-5", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]

    def complete(self, system: str, prompt: str) -> str:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 1500,
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
